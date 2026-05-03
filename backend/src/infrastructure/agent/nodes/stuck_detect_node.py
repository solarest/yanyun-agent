"""基础设施层 - Stuck 检测节点(增强版)

LangGraph Node: stuck_detect_node
职责:
1. 评估 LLM 纯文本输出(新增,原 answer_observe 职责)
2. 检测 Agent 是否卡住(无法推进任务)
3. 内部处理反馈注入与升级策略(吸收原 stuck_feedback_node)
4. 预算耗尽检查
"""

import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.types import RunnableConfig

from src.domain.entities.agent_state import AgentState
from src.infrastructure.agent.nodes.observe import (
    emit_decision,
    emit_phase_safe,
    emit_safe,
    exhausted_turn_budget,
    extract_final_result,
    extract_text,
    get_event_emitter,
)

logger = logging.getLogger(__name__)

# 全局纠正预算:空响应/循环/卡住计数累计达到此阈值即终止
GLOBAL_CORRECTION_BUDGET = 3

# 重试限制
EMPTY_MAX_RETRY = 1
PLANNING_MAX_RETRY = 2


# === LLM 文本输出评估(原 answer_observe 职责) ===


def _evaluate_llm_text(text: str) -> dict:
    """评估 LLM 纯文本输出(规则判断)

    优先级链:
    1. 空响应: text为空/纯空白
    2. 完成声明: 包含"任务完成"/"已经完成"/"task complete"等关键词
    3. 用户提问: 末尾以"?"/"？"结尾或包含"请问"/"是否"/"还需要"
    4. 纯规划: 包含"我将要"/"步骤如下"/"计划"但无"已完成"/"已创建"
    5. 实质性文本: 默认路径

    Returns:
        {
            "category": "empty" | "complete" | "incomplete" | "user_question" | "planning_only" | "substantive_text",
            "route": "llm_call" | "complete" | "terminate" | "handle_empty" | "handle_planning",
            "has_substance": bool (仅 complete 类别)
        }
    """
    if not text or not text.strip():
        return {"category": "empty", "route": "handle_empty"}

    text_lower = text.lower()

    # 完成声明检测
    completion_keywords = [
        "任务完成", "已经完成", "task complete", "i have completed",
        "task is done", "work is complete", "finished the task"
    ]
    has_completion = any(kw in text_lower for kw in completion_keywords)

    if has_completion:
        # 实质性验证(检查是否有具体内容)
        has_substance = len(text.strip()) > 100 and (
            "文件" in text or "file" in text_lower or
            "创建" in text or "created" in text_lower or
            "修改" in text or "modified" in text_lower or
            "删除" in text or "deleted" in text_lower or
            "实现" in text or "implemented" in text_lower
        )

        if has_substance:
            return {"category": "complete", "route": "complete", "has_substance": True}
        else:
            return {"category": "incomplete", "route": "llm_call", "has_substance": False}

    # 用户提问检测
    if text.rstrip().endswith(("?", "？")) or any(kw in text for kw in ["请问", "是否", "还需要", "你希望", "请告诉我"]):
        return {"category": "user_question", "route": "complete"}

    # 纯规划检测
    planning_keywords = ["我将要", "步骤如下", "计划",
                         "下一步", "i will", "steps:", "plan:"]
    action_keywords = ["已创建", "已修改", "已完成",
                       "created", "modified", "done", "implemented"]
    has_planning = any(kw in text for kw in planning_keywords)
    has_action = any(kw in text for kw in action_keywords)

    if has_planning and not has_action:
        return {"category": "planning_only", "route": "handle_planning"}

    # 默认: 实质性文本
    return {"category": "substantive_text", "route": "continue"}


async def _handle_empty_response(state: AgentState, event_emitter: Any, task_id: str, current_turn: int) -> dict:
    """处理空响应"""
    count = state.get("empty_retry_count", 0) + 1

    correction_total = (
        count
        + int(state.get("loop_detection_count", 0) or 0)
        + int(state.get("stuck_detection_count", 0) or 0)
    )

    if (
        count > EMPTY_MAX_RETRY
        or correction_total >= GLOBAL_CORRECTION_BUDGET
        or exhausted_turn_budget(state)
    ):
        if correction_total >= GLOBAL_CORRECTION_BUDGET and count <= EMPTY_MAX_RETRY:
            reason = "global_correction_budget_exhausted"
        elif count > EMPTY_MAX_RETRY:
            reason = "empty_max_retry"
        else:
            reason = "budget_exhausted"

        logger.error(
            "Empty response unrecoverable (%s). Terminating. correction_total=%d",
            reason, correction_total,
        )
        await emit_decision(event_emitter, task_id, current_turn, "terminate", f"empty:{reason}")

        return {
            "empty_retry_count": count,
            "should_end": True,
            "error": "Empty response persists after correction",
            "final_result": extract_final_result(state),
            "phase": "complete",
        }

    await emit_decision(event_emitter, task_id, current_turn, "llm_call", f"empty:retry_{count}")

    final_result = extract_final_result(state)
    if final_result:
        logger.warning(
            "Empty response but valid result exists. Terminating with result. count=%d", count)
        return {
            "empty_retry_count": count,
            "should_end": True,
            "final_result": final_result,
            "phase": "complete",
        }

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


async def _handle_completion_claim(state: AgentState, event_emitter: Any, task_id: str, current_turn: int, text: str) -> dict:
    """处理完成声明(有实质内容)"""
    logger.info("Completion claim validated, task complete")
    await emit_safe(
        event_emitter,
        task_id,
        "completion:validated",
        {"turn": current_turn, "quality": "complete", "summary": text[:200]},
    )
    await emit_decision(event_emitter, task_id, current_turn, "complete", "completion_validated")

    return {
        "phase": "complete",
        "final_result": text,
        "is_complete": True,
        "should_end": True,
        "observation_summary": "Task completion validated",
    }


async def _handle_incomplete_completion(state: AgentState, event_emitter: Any, task_id: str, current_turn: int, text: str) -> dict:
    """处理完成声明(缺少实质内容)"""
    logger.info("Completion claim lacks substance, injecting feedback")

    if exhausted_turn_budget(state):
        return {
            "error": f"Max turns ({state.get('max_turns', 100)}) reached after incomplete completion",
            "should_end": True,
            "final_result": text,
        }

    await emit_decision(event_emitter, task_id, current_turn, "llm_call", "completion_lacks_substance")

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


async def _handle_user_question(event_emitter: Any, task_id: str, current_turn: int, text: str) -> dict:
    """处理用户提问"""
    await emit_decision(event_emitter, task_id, current_turn, "complete", "user_question")
    return {
        "phase": "complete",
        "final_result": text,
        "is_complete": True,
        "should_end": True,
    }


async def _handle_planning_only(state: AgentState, event_emitter: Any, task_id: str, current_turn: int) -> dict:
    """处理纯规划(无行动)"""
    count = state.get("planning_retry_count", 0) + 1

    if count > PLANNING_MAX_RETRY or exhausted_turn_budget(state):
        reason = "planning_max_retry" if count > PLANNING_MAX_RETRY else "budget_exhausted"
        await emit_decision(event_emitter, task_id, current_turn, "terminate", f"planning:{reason}")
        return {
            "planning_retry_count": count,
            "error": "Planning-only persists after correction",
            "should_end": True,
            "final_result": extract_final_result(state),
        }

    await emit_decision(event_emitter, task_id, current_turn, "llm_call", f"planning:retry_{count}")
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
            "[NODE:stuck_detect] NO_STUCK | task_id=%s | turn=%d | "
            "no_tool_calls_count=%d/3",
            task_id, current_turn, no_tool_calls_count
        )
        return {"stuck_detected": False, "stuck_type": None, "stuck_detection_count": 0}

    # === Stuck 检测到:内部处理反馈与升级策略 ===
    event_emitter = get_event_emitter(config)
    previous_phase = state.get("phase", "thinking")
    next_count = state.get("stuck_detection_count", 0) + 1
    stuck_type = "monologue"
    action = "terminate" if next_count >= 3 else "inject_feedback"

    # Stuck 检测日志
    logger.info(
        "[NODE:stuck_detect] STUCK_DETECTED | task_id=%s | turn=%d | "
        "stuck_type=%s | detection_count=%d | action=%s",
        task_id, current_turn, stuck_type, next_count, action
    )

    await event_emitter.emit(
        state["task_id"],
        "stuck:detected",
        {
            "stuckType": stuck_type,
            "count": next_count,
            "action": action,
        },
    )
    await emit_phase_safe(event_emitter, state["task_id"], "stuck_recovering", previous_phase, current_turn)

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
        terminate_reason = (
            stuck_type if next_count >= 3 else "global_correction_budget_exhausted"
        )
        logger.error(
            "[NODE:stuck_detect] STUCK_TERMINATE | task_id=%s | turn=%d | "
            "detection_count=%d | correction_total=%d | stuck_type=%s | reason=%s",
            task_id, current_turn, next_count, correction_total, stuck_type,
            terminate_reason,
        )
        base_update["error"] = (
            f"Stuck detected ({stuck_type}), unrecoverable"
            if next_count >= 3
            else "Global correction budget exhausted"
        )
        base_update["should_end"] = True
        return base_update

    if exhausted_turn_budget(state):
        max_turns = state.get("max_turns", 100)
        logger.error(
            "[NODE:stuck_detect] BUDGET_EXHAUSTED | task_id=%s | turn=%d/%d | "
            "reason=stuck_recovery",
            task_id, current_turn, max_turns
        )
        base_update["error"] = f"Max turns ({max_turns}) reached during stuck recovery"
        base_update["should_end"] = True
        return base_update

    # 注入反馈
    logger.warning(
        "[NODE:stuck_detect] FEEDBACK_INJECT | task_id=%s | turn=%d | "
        "stuck_type=%s | detection_count=%d | correction_total=%d",
        task_id, current_turn, stuck_type, next_count, correction_total,
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


async def stuck_detect_node(state: AgentState, config: RunnableConfig) -> dict:
    """Stuck 检测节点(增强版)

    职责:
    1. 评估 LLM 文本输出(新增,原 answer_observe 职责)
    2. 检测 monologue 模式(连续无工具调用)
    3. 内部处理反馈注入与升级策略

    Args:
        state: 当前 Agent 状态
        config: LangGraph 配置

    Returns:
        状态更新字典
    """
    task_id = state.get("task_id", "")
    current_turn = state.get("current_turn", 0)
    agent_id = config.get("configurable", {}).get("agent_id", "unknown")
    event_emitter = get_event_emitter(config)

    # Node 入口日志
    logger.info(
        "[NODE:stuck_detect] START | agent_id=%s | task_id=%s | turn=%d | "
        "empty_retry_count=%d | messages_count=%d",
        agent_id, task_id, current_turn,
        state.get("empty_retry_count", 0), len(state.get("messages", []))
    )

    messages = state.get("messages", [])
    if not messages:
        logger.info(
            "[NODE:stuck_detect] NO_MESSAGES | task_id=%s | turn=%d", task_id, current_turn)
        return {"phase": "thinking"}

    last_msg = messages[-1]
    text = extract_text(last_msg)

    # 步骤1: 评估 LLM 文本输出
    text_eval = _evaluate_llm_text(text)

    # 处理空响应
    if text_eval["category"] == "empty":
        logger.info(
            "[NODE:stuck_detect] EMPTY_TEXT_DETECTED | task_id=%s | turn=%d", task_id, current_turn)
        return await _handle_empty_response(state, event_emitter, task_id, current_turn)

    # 处理完成声明(有实质内容)
    if text_eval["category"] == "complete":
        return await _handle_completion_claim(state, event_emitter, task_id, current_turn, text)

    # 处理完成声明(缺少实质内容)
    if text_eval["category"] == "incomplete":
        return await _handle_incomplete_completion(state, event_emitter, task_id, current_turn, text)

    # 处理用户提问
    if text_eval["category"] == "user_question":
        return await _handle_user_question(event_emitter, task_id, current_turn, text)

    # 处理纯规划
    if text_eval["category"] == "planning_only":
        return await _handle_planning_only(state, event_emitter, task_id, current_turn)

    # 步骤2: 检测 monologue 模式(连续无工具调用)
    # (实质性文本且未归类为其他场景)
    stuck_result = await _detect_monologue(state, config)

    # 如果未卡住,继续 llm_call
    if not stuck_result.get("stuck_detected"):
        return {"phase": "thinking"}

    return stuck_result
