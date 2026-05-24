"""基础设施层 - Stuck 检测节点(增强版)

LangGraph Node: stuck_detect_node
职责:
1. 评估 LLM 纯文本输出(新增,原 answer_observe 职责) - 使用 LLM 智能分类
2. 检测 Agent 是否卡住(无法推进任务)
3. 内部处理反馈注入与升级策略(吸收原 stuck_feedback_node)
4. 预算耗尽检查
"""

import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.types import RunnableConfig

from src.domain.agent.agent_state import AgentState
from src.infrastructure.agent.nodes.base_node import BaseNode, NodeContext
from src.infrastructure.llm.model_factory import create_chat_model

logger = logging.getLogger(__name__)

# 全局纠正预算:空响应/循环/卡住计数累计达到此阈值即终止
GLOBAL_CORRECTION_BUDGET = 3

# 重试限制
EMPTY_MAX_RETRY = 1
PLANNING_MAX_RETRY = 2

# LLM 分类配置
CLASSIFICATION_LLM_TEMPERATURE = 0.1  # 低温度保证分类稳定性
CLASSIFICATION_MAX_TOKENS = 200


# === 节点内部使用的辅助函数 ===


def _get_event_emitter(config: RunnableConfig) -> Any:
    """从配置中获取事件发射器"""
    return (config.get("configurable") or {}).get("event_emitter") or (
        config.get("configurable") or {}
    ).get("event_service")


def _exhausted_turn_budget(state: AgentState) -> bool:
    """检查是否已耗尽 turn 预算"""
    return state.get("current_turn", 0) >= state.get("max_turns", 100)


def _extract_text(msg: Any) -> str:
    """从消息中提取文本内容"""
    try:
        if isinstance(msg, dict):
            return msg.get("content", "") or ""
        elif hasattr(msg, "content"):
            return msg.content or ""
        return ""
    except Exception as e:
        logger.warning("Failed to extract text from message: %s", e)
        return ""


def _extract_final_result(state: AgentState) -> str:
    """提取最终结果"""
    if state.get("final_result"):
        return state["final_result"]
    messages = state.get("messages", [])
    if messages:
        return _extract_text(messages[-1])
    return ""


async def _emit_decision(
    event_emitter: Any,
    task_id: str,
    current_turn: int,
    route_hint: str,
    reason: str,
) -> None:
    """发射决策事件"""
    if event_emitter is None:
        return
    try:
        import inspect
        method = event_emitter.emit
        if inspect.iscoroutinefunction(method):
            await method(
                task_id,
                "observe:decision",
                {
                    "turn": current_turn,
                    "routeHint": route_hint,
                    "reason": reason,
                },
            )
        else:
            method(
                task_id,
                "observe:decision",
                {
                    "turn": current_turn,
                    "routeHint": route_hint,
                    "reason": reason,
                },
            )
    except Exception as exc:
        logger.warning("observe event emit failed: %s", exc)

# 分类 LLM 实例缓存(独立于 Agent Loop 的主 LLM)
_classification_llm_cache = None


def _get_classification_llm():
    """获取分类用的独立 LLM 实例(带缓存)

    这个 LLM 实例:
    - 使用 temperature=0.1 保证分类稳定性
    - 不绑定 tools(只需要文本分类能力)
    - 独立于 Agent Loop 的主 LLM 实例
    """
    global _classification_llm_cache
    if _classification_llm_cache is None:
        _classification_llm_cache = create_chat_model(
            temperature=CLASSIFICATION_LLM_TEMPERATURE)
    return _classification_llm_cache


async def _classify_llm_output(text: str, llm) -> dict:
    """使用 LLM 分类文本输出

    Args:
        text: LLM 输出的文本内容
        llm: LLM 实例

    Returns:
        {
            "category": "empty" | "complete" | "incomplete" | "user_question" | "planning_only" | "substantive_text",
            "route": "llm_call" | "complete" | "terminate" | "handle_empty" | "handle_planning",
            "confidence": float (0-1),
            "reasoning": str (可选)
        }
    """
    prompt = f"""你是一个 Agent 工作流中的文本输出分类器。请分析 LLM 的输出文本,将其归类到以下类别之一。

## 分类类别

1. **empty**: 空响应或纯空白内容
2. **complete**: 明确表示任务已完成,且包含具体的工作成果描述(文件创建/修改/删除、功能实现等)
3. **incomplete**: 声称任务完成,但缺少具体的工作成果或细节描述
4. **user_question**: 向用户提出问题,包括澄清问题、需要用户选择或确认
5. **planning_only**: 描述了将要执行的计划、步骤或意图,但尚未实际执行任何操作
6. **substantive_text**: 包含实质性内容,如分析结果、工具调用说明、工作进展等

## Few-Shot 示例

### 示例 1: empty
输入: ""
输出: {{"category": "empty", "confidence": 1.0}}

### 示例 2: complete
输入: "任务完成。我已经创建了用户管理模块,包括用户注册、登录和权限验证功能。文件已保存到 src/users/ 目录下。"
输出: {{"category": "complete", "confidence": 0.95, "reasoning": "明确声明完成,且包含具体的工作成果"}}

### 示例 3: incomplete
输入: "任务完成"
输出: {{"category": "incomplete", "confidence": 0.9, "reasoning": "声称完成但无任何具体成果描述"}}

### 示例 4: user_question
输入: "我需要了解您的具体需求。请问您希望实现什么功能?请选择: 1. 数据分析 2. 文件处理"
输出: {{"category": "user_question", "confidence": 0.95}}

### 示例 5: planning_only
输入: "我将要执行以下步骤:\n1. 读取配置文件\n2. 分析数据结构\n3. 创建处理函数"
输出: {{"category": "planning_only", "confidence": 0.9, "reasoning": "描述了计划但未执行"}}

### 示例 6: substantive_text
输入: "通过分析代码库,我发现主要问题在于数据库连接池配置不当。建议调整以下参数..."
输出: {{"category": "substantive_text", "confidence": 0.95}}

## 当前输入

输入文本: {text}

## 输出要求

请以 JSON 格式返回,仅包含以下字段:
- category: 类别名称(必填)
- confidence: 置信度 0-1(必填)
- reasoning: 简短的推理说明(可选,1-2句话)

只返回 JSON,不要其他内容。"""

    response = await llm.ainvoke(prompt)
    response_text = response.content.strip()

    # 解析 JSON 响应
    try:
        # 尝试提取 JSON(可能包含在代码块中)
        if "```" in response_text:
            json_str = response_text.split("```")[1]
            if json_str.startswith("json"):
                json_str = json_str[4:].strip()
        else:
            json_str = response_text

        result = json.loads(json_str)

        # 验证必要字段
        if "category" not in result:
            raise ValueError("Missing 'category' field")

        # 映射 category 到 route
        category = result["category"]
        route_mapping = {
            "empty": "handle_empty",
            "complete": "complete",
            "incomplete": "llm_call",
            "user_question": "complete",
            "planning_only": "handle_planning",
            "substantive_text": "continue",
        }

        return {
            "category": category,
            "route": route_mapping.get(category, "continue"),
            "confidence": result.get("confidence", 0.0),
            "reasoning": result.get("reasoning", ""),
        }

    except (json.JSONDecodeError, ValueError, IndexError) as e:
        logger.warning(
            "Failed to parse LLM classification result: %s, response: %s", e, response_text[
                :200]
        )
        # 降级到规则判断
        return _fallback_evaluate_llm_text(text)


def _fallback_evaluate_llm_text(text: str) -> dict:
    """降级规则: 当 LLM 调用失败或解析失败时使用

    仅处理最基本的情况(空响应),其他情况默认继续
    """
    if not text or not text.strip():
        return {"category": "empty", "route": "handle_empty"}

    # 极简规则,仅处理空响应,其他都当作实质性文本
    return {"category": "substantive_text", "route": "continue"}


async def _handle_empty_response(
    state: AgentState, event_emitter: Any, task_id: str, current_turn: int
) -> dict:
    """处理空响应"""
    count = state.get("empty_retry_count", 0) + 1

    logger.info(
        "[NODE:stuck_detect] HANDLE_EMPTY | task_id=%s | turn=%d | empty_retry_count=%d",
        task_id,
        current_turn,
        count,
    )

    correction_total = (
        count
        + int(state.get("loop_detection_count", 0) or 0)
        + int(state.get("stuck_detection_count", 0) or 0)
    )

    logger.info(
        "[NODE:stuck_detect] EMPTY_CHECK_TERMINATE | task_id=%s | turn=%d | "
        "count=%d | correction_total=%d | max_retry=%d | global_budget=%d | budget_exhausted=%s",
        task_id,
        current_turn,
        count,
        correction_total,
        EMPTY_MAX_RETRY,
        GLOBAL_CORRECTION_BUDGET,
        _exhausted_turn_budget(state),
    )

    if (
        count > EMPTY_MAX_RETRY
        or correction_total >= GLOBAL_CORRECTION_BUDGET
        or _exhausted_turn_budget(state)
    ):
        if correction_total >= GLOBAL_CORRECTION_BUDGET and count <= EMPTY_MAX_RETRY:
            reason = "global_correction_budget_exhausted"
        elif count > EMPTY_MAX_RETRY:
            reason = "empty_max_retry"
        else:
            reason = "budget_exhausted"

        logger.error(
            "[NODE:stuck_detect] EMPTY_TERMINATE | task_id=%s | turn=%d | "
            "reason=%s | correction_total=%d | count=%d",
            task_id,
            current_turn,
            reason,
            correction_total,
            count,
        )
        await _emit_decision(event_emitter, task_id, current_turn, "terminate", f"empty:{reason}")

        return {
            "empty_retry_count": count,
            "should_end": True,
            "error": "Empty response persists after correction",
            "final_result": _extract_final_result(state),
            "phase": "complete",
        }

    logger.info(
        "[NODE:stuck_detect] EMPTY_RETRY | task_id=%s | turn=%d | count=%d | will_retry_llm",
        task_id,
        current_turn,
        count,
    )
    await _emit_decision(event_emitter, task_id, current_turn, "llm_call", f"empty:retry_{count}")

    final_result = _extract_final_result(state)
    if final_result:
        logger.warning(
            "[NODE:stuck_detect] EMPTY_HAS_RESULT | task_id=%s | turn=%d | "
            "count=%d | has_valid_result, terminating",
            task_id,
            current_turn,
            count,
        )
        return {
            "empty_retry_count": count,
            "should_end": True,
            "final_result": final_result,
            "phase": "complete",
        }

    logger.info(
        "[NODE:stuck_detect] EMPTY_INJECT_FEEDBACK | task_id=%s | turn=%d | "
        "count=%d | injecting_system_correction",
        task_id,
        current_turn,
        count,
    )
    return {
        "empty_retry_count": count,
        "messages": [
            SystemMessage(
                content=(
                    "[SYSTEM CORRECTION] Your previous response was empty. "
                    "Please continue working on the task. "
                    "If you're unsure about the next step, read relevant files first."
                )
            )
        ],
        "phase": "thinking",
    }


async def _handle_completion_claim(
    state: AgentState, event_emitter: Any, task_id: str, current_turn: int, text: str
) -> dict:
    """处理完成声明(有实质内容)"""
    logger.info(
        "[NODE:stuck_detect] HANDLE_COMPLETION | task_id=%s | turn=%d | "
        "text_length=%d | validated_complete",
        task_id,
        current_turn,
        len(text),
    )
    await event_emitter.emit_safe(
        task_id,
        "completion:validated",
        {"turn": current_turn, "quality": "complete", "summary": text[:200]},
    )
    await _emit_decision(event_emitter, task_id, current_turn, "complete", "completion_validated")

    return {
        "phase": "complete",
        "final_result": text,
        "is_complete": True,
        "should_end": True,
        "observation_summary": "Task completion validated",
    }


async def _handle_incomplete_completion(
    state: AgentState, event_emitter: Any, task_id: str, current_turn: int, text: str
) -> dict:
    """处理完成声明(缺少实质内容)"""
    logger.info(
        "[NODE:stuck_detect] HANDLE_INCOMPLETE_COMPLETION | task_id=%s | turn=%d | "
        "text_length=%d | injecting_feedback",
        task_id,
        current_turn,
        len(text),
    )

    if _exhausted_turn_budget(state):
        max_turns = state.get("max_turns", 100)
        logger.error(
            "[NODE:stuck_detect] INCOMPLETE_BUDGET_EXHAUSTED | task_id=%s | turn=%d/%d",
            task_id,
            current_turn,
            max_turns,
        )
        return {
            "error": f"Max turns ({state.get('max_turns', 100)}) reached after incomplete completion",
            "should_end": True,
            "final_result": text,
        }

    logger.info(
        "[NODE:stuck_detect] INCOMPLETE_INJECT_FEEDBACK | task_id=%s | turn=%d | will_continue_llm",
        task_id,
        current_turn,
    )
    await _emit_decision(
        event_emitter, task_id, current_turn, "llm_call", "completion_lacks_substance"
    )

    return {
        "messages": [
            HumanMessage(
                content=(
                    "You claimed the task is complete, but it appears there is still work to do. "
                    "Please continue working on the task and provide detailed results."
                )
            )
        ],
        "observation_summary": "Completion claim lacks details",
        "phase": "thinking",
    }


async def _handle_user_question(
    event_emitter: Any, task_id: str, current_turn: int, text: str
) -> dict:
    """处理用户提问"""
    logger.info(
        "[NODE:stuck_detect] HANDLE_USER_QUESTION | task_id=%s | turn=%d | "
        "text_length=%d | completing",
        task_id,
        current_turn,
        len(text),
    )
    await _emit_decision(event_emitter, task_id, current_turn, "complete", "user_question")
    return {
        "phase": "complete",
        "final_result": text,
        "is_complete": True,
        "should_end": True,
    }


async def _handle_planning_only(
    state: AgentState, event_emitter: Any, task_id: str, current_turn: int
) -> dict:
    """处理纯规划(无行动)"""
    count = state.get("planning_retry_count", 0) + 1

    logger.info(
        "[NODE:stuck_detect] HANDLE_PLANNING | task_id=%s | turn=%d | planning_retry_count=%d",
        task_id,
        current_turn,
        count,
    )

    if count > PLANNING_MAX_RETRY or _exhausted_turn_budget(state):
        reason = "planning_max_retry" if count > PLANNING_MAX_RETRY else "budget_exhausted"
        max_turns = state.get("max_turns", 100)
        logger.error(
            "[NODE:stuck_detect] PLANNING_TERMINATE | task_id=%s | turn=%d | "
            "reason=%s | count=%d | max_turns=%d",
            task_id,
            current_turn,
            reason,
            count,
            max_turns,
        )
        await _emit_decision(event_emitter, task_id, current_turn, "terminate", f"planning:{reason}")
        return {
            "planning_retry_count": count,
            "error": "Planning-only persists after correction",
            "should_end": True,
            "final_result": _extract_final_result(state),
        }

    logger.info(
        "[NODE:stuck_detect] PLANNING_RETRY | task_id=%s | turn=%d | count=%d | will_retry_llm",
        task_id,
        current_turn,
        count,
    )
    await _emit_decision(event_emitter, task_id, current_turn, "llm_call", f"planning:retry_{count}")
    return {
        "planning_retry_count": count,
        "messages": [
            SystemMessage(
                content=(
                    "[SYSTEM CORRECTION] You outlined a plan but haven't taken action yet. "
                    "Please proceed with executing the plan using the available tools."
                )
            )
        ],
        "phase": "thinking",
    }


# === Stuck 检测逻辑 ===


def _assistant_message(msg) -> dict | None:
    if isinstance(msg, dict) and msg.get("role") == "assistant":
        return {
            "content": msg.get("content", "") or "",
            "tool_calls": msg.get("tool_calls") or [],
        }
    if isinstance(msg, AIMessage):
        return {
            "content": msg.content or "",
            "tool_calls": msg.tool_calls or [],
        }
    return None


async def _detect_monologue(state: AgentState, config: RunnableConfig) -> dict:
    """检测 monologue 模式(连续无工具调用)"""
    task_id = state.get("task_id", "")
    current_turn = state.get("current_turn", 0)

    start_index = state.get("task_start_message_count", 0)
    messages = state["messages"][start_index:]

    # 检查最近几轮是否有实质进展
    recent_assistant_msgs = []
    for msg in reversed(messages):
        assistant_msg = _assistant_message(msg)
        if assistant_msg is not None:
            recent_assistant_msgs.append(assistant_msg)
            if len(recent_assistant_msgs) >= 3:
                break

    # 检查是否连续没有工具调用
    no_tool_calls_count = 0
    for msg in recent_assistant_msgs:
        if not msg.get("tool_calls"):
            no_tool_calls_count += 1

    if no_tool_calls_count < 3:
        # 未检测到卡住
        logger.info(
            "[NODE:stuck_detect] NO_STUCK | task_id=%s | turn=%d | no_tool_calls_count=%d/3",
            task_id,
            current_turn,
            no_tool_calls_count,
        )
        return {"stuck_detected": False, "stuck_type": None, "stuck_detection_count": 0}

    # === Stuck 检测到:内部处理反馈与升级策略 ===
    event_emitter = _get_event_emitter(config)
    previous_phase = state.get("phase", "thinking")
    next_count = state.get("stuck_detection_count", 0) + 1
    stuck_type = "monologue"
    action = "terminate" if next_count >= 3 else "inject_feedback"

    # Stuck 检测日志
    logger.info(
        "[NODE:stuck_detect] STUCK_DETECTED | task_id=%s | turn=%d | "
        "stuck_type=%s | detection_count=%d | action=%s",
        task_id,
        current_turn,
        stuck_type,
        next_count,
        action,
    )

    await event_emitter.emit_safe(
        state["task_id"],
        "stuck:detected",
        {
            "stuckType": stuck_type,
            "count": next_count,
            "action": action,
        },
    )
    await event_emitter.emit_phase_changed_safe(
        state["task_id"], "stuck_recovering", previous_phase, current_turn
    )

    base_update = {
        "stuck_detected": True,
        "stuck_detection_count": next_count,
        "stuck_type": stuck_type,
        "phase": "stuck_recovering",
    }

    # 升级策略处理
    correction_total = (
        int(state.get("empty_retry_count", 0) or 0)
        + int(state.get("loop_detection_count", 0) or 0)
        + int(next_count or 0)
    )
    if next_count >= 3 or correction_total >= GLOBAL_CORRECTION_BUDGET:
        terminate_reason = stuck_type if next_count >= 3 else "global_correction_budget_exhausted"
        logger.error(
            "[NODE:stuck_detect] STUCK_TERMINATE | task_id=%s | turn=%d | "
            "detection_count=%d | correction_total=%d | stuck_type=%s | reason=%s",
            task_id,
            current_turn,
            next_count,
            correction_total,
            stuck_type,
            terminate_reason,
        )
        base_update["error"] = (
            f"Stuck detected ({stuck_type}), unrecoverable"
            if next_count >= 3
            else "Global correction budget exhausted"
        )
        base_update["should_end"] = True
        return base_update

    if _exhausted_turn_budget(state):
        max_turns = state.get("max_turns", 100)
        logger.error(
            "[NODE:stuck_detect] BUDGET_EXHAUSTED | task_id=%s | turn=%d/%d | "
            "reason=stuck_recovery",
            task_id,
            current_turn,
            max_turns,
        )
        base_update["error"] = f"Max turns ({max_turns}) reached during stuck recovery"
        base_update["should_end"] = True
        return base_update

    # 注入反馈
    logger.warning(
        "[NODE:stuck_detect] FEEDBACK_INJECT | task_id=%s | turn=%d | "
        "stuck_type=%s | detection_count=%d | correction_total=%d",
        task_id,
        current_turn,
        stuck_type,
        next_count,
        correction_total,
    )
    if stuck_type == "monologue":
        content = (
            "[SYSTEM CORRECTION] You have been providing analysis without taking action. "
            "Please use an appropriate tool to make progress on the task. "
            "If you need more information, use the available tools first."
        )
    else:
        content = (
            "[SYSTEM CORRECTION] You appear to be stuck. "
            "Please try a different approach to make progress on the task."
        )

    base_update["messages"] = [SystemMessage(content=content)]
    return base_update


# === 节点入口 ===


class StuckDetectNode(BaseNode):
    """Stuck 检测节点(增强版)"""

    @property
    def node_name(self) -> str:
        return "stuck_detect"

    @property
    def default_phase(self) -> str | None:
        return None  # 此节点内部自行控制 phase

    async def execute(self, state: AgentState, config: RunnableConfig, context: NodeContext) -> dict:
        """执行 Stuck 检测

        职责:
        1. 评估 LLM 文本输出(新增,原 answer_observe 职责) - 使用 LLM 智能分类
        2. 检测 monologue 模式(连续无工具调用)
        3. 内部处理反馈注入与升级策略

        Args:
            state: 当前 Agent 状态
            config: LangGraph 配置
            context: 节点执行上下文

        Returns:
            状态更新字典
        """
        task_id = context.task_id
        current_turn = context.current_turn
        event_emitter = context.event_emitter

        # Node 入口日志(将由基类自动记录)
        logger.info(
            "[NODE:stuck_detect] START | agent_id=%s | task_id=%s | turn=%d | "
            "phase=%s | empty_retry_count=%d | planning_retry_count=%d | "
            "stuck_detection_count=%d | loop_detection_count=%d | messages_count=%d",
            context.agent_id,
            task_id,
            current_turn,
            state.get("phase", "unknown"),
            state.get("empty_retry_count", 0),
            state.get("planning_retry_count", 0),
            state.get("stuck_detection_count", 0),
            state.get("loop_detection_count", 0),
            len(state.get("messages", [])),
        )

        messages = state.get("messages", [])
        if not messages:
            logger.info(
                "[NODE:stuck_detect] NO_MESSAGES | task_id=%s | turn=%d", task_id, current_turn)
            return {"phase": "thinking"}

        last_msg = messages[-1]
        text = _extract_text(last_msg)

        # 步骤1: 评估 LLM 文本输出(使用独立的分类 LLM)
        try:
            # 使用独立的分类 LLM 实例(不污染 Agent Loop 的主 LLM)
            classification_llm = _get_classification_llm()
            text_eval = await _classify_llm_output(text, classification_llm)
            logger.info(
                "[NODE:stuck_detect] LLM_CLASSIFY | task_id=%s | turn=%d | "
                "category=%s | confidence=%.2f | reasoning=%s",
                task_id,
                current_turn,
                text_eval["category"],
                text_eval.get("confidence", 0),
                text_eval.get("reasoning", ""),
            )
        except Exception as e:
            logger.warning(
                "[NODE:stuck_detect] LLM_CLASSIFY_FALLBACK | task_id=%s | turn=%d | error=%s",
                task_id,
                current_turn,
                str(e),
            )
            text_eval = _fallback_evaluate_llm_text(text)
            logger.info(
                "[NODE:stuck_detect] FALLBACK_EVAL | task_id=%s | turn=%d | category=%s | route=%s",
                task_id,
                current_turn,
                text_eval["category"],
                text_eval["route"],
            )

        # 处理空响应
        if text_eval["category"] == "empty":
            logger.info(
                "[NODE:stuck_detect] BRANCH:Empty_TEXT | task_id=%s | turn=%d | route=%s",
                task_id,
                current_turn,
                text_eval["route"],
            )
            return await _handle_empty_response(state, event_emitter, task_id, current_turn)

        # 处理完成声明(有实质内容)
        if text_eval["category"] == "complete":
            logger.info(
                "[NODE:stuck_detect] BRANCH:COMPLETION_VALIDATED | task_id=%s | turn=%d | "
                "text_length=%d",
                task_id,
                current_turn,
                len(text),
            )
            return await _handle_completion_claim(state, event_emitter, task_id, current_turn, text)

        # 处理完成声明(缺少实质内容)
        if text_eval["category"] == "incomplete":
            logger.info(
                "[NODE:stuck_detect] BRANCH:COMPLETION_INCOMPLETE | task_id=%s | turn=%d | "
                "text_length=%d",
                task_id,
                current_turn,
                len(text),
            )
            return await _handle_incomplete_completion(
                state, event_emitter, task_id, current_turn, text
            )

        # 处理用户提问
        if text_eval["category"] == "user_question":
            logger.info(
                "[NODE:stuck_detect] BRANCH:USER_QUESTION | task_id=%s | turn=%d | text_length=%d",
                task_id,
                current_turn,
                len(text),
            )
            return await _handle_user_question(event_emitter, task_id, current_turn, text)

        # 处理纯规划
        if text_eval["category"] == "planning_only":
            logger.info(
                "[NODE:stuck_detect] BRANCH:PLANNING_ONLY | task_id=%s | turn=%d | route=%s",
                task_id,
                current_turn,
                text_eval["route"],
            )
            return await _handle_planning_only(state, event_emitter, task_id, current_turn)

        # 步骤2: 检测 monologue 模式(连续无工具调用)
        # (实质性文本且未归类为其他场景)
        logger.info(
            "[NODE:stuck_detect] BRANCH:SUBSTANTIVE_TEXT | task_id=%s | turn=%d | "
            "proceeding_to_monologue_detection",
            task_id,
            current_turn,
        )
        stuck_result = await _detect_monologue(state, config)

        # 如果未卡住,继续 llm_call
        if not stuck_result.get("stuck_detected"):
            logger.info(
                "[NODE:stuck_detect] BRANCH:CONTINUE | task_id=%s | turn=%d | phase=thinking",
                task_id,
                current_turn,
            )
            return {"phase": "thinking"}

        # 卡住,返回 stuck 处理结果
        logger.info(
            "[NODE:stuck_detect] BRANCH:STUCK_RECOVERY | task_id=%s | turn=%d | stuck_type=%s",
            task_id,
            current_turn,
            stuck_result.get("stuck_type"),
        )
        return stuck_result


# 保持向后兼容的实例导出
stuck_detect_node = StuckDetectNode()
