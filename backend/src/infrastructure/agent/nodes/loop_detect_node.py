"""基础设施层 - Loop 检测节点(增强版)

LangGraph Node: loop_detect_node
职责:
1. 检测无效工具调用(INVALID_TOOL_CALL)
2. 检测工具调用模式重复(精确匹配 + A-B-A-B交替)
3. 内部处理反馈注入与升级策略
4. 预算耗尽检查

触发时机: 仅在 llm_call 之后、tool_execute 之前执行
"""

import hashlib
import inspect
import json
import logging
from typing import Any

from langchain_core.messages import SystemMessage
from langgraph.types import RunnableConfig

from src.domain.entities.agent_state import AgentState
from src.infrastructure.agent.nodes.base_node import BaseNode, NodeContext

logger = logging.getLogger(__name__)

# 全局纠正预算:空响应/循环/卡住计数累计达到此阈值即终止
GLOBAL_CORRECTION_BUDGET = 3


# === 辅助函数 ===


def _get_event_emitter(config: RunnableConfig) -> Any:
    """从配置中获取事件发射器"""
    return (config.get("configurable") or {}).get("event_emitter") or (
        config.get("configurable") or {}
    ).get("event_service")


async def _emit_safe(emitter: Any, *args: Any, **kwargs: Any) -> None:
    """安全地发射事件，忽略异常"""
    if emitter is None:
        return
    try:
        method = emitter.emit
        if inspect.iscoroutinefunction(method):
            await method(*args, **kwargs)
        else:
            method(*args, **kwargs)
    except Exception as exc:
        logger.warning("event emit failed: %s", exc)


async def _emit_phase_safe(emitter: Any, *args: Any) -> None:
    """安全地发射阶段变更事件，忽略异常"""
    if emitter is None:
        return
    try:
        method = emitter.emit_phase_changed
        if inspect.iscoroutinefunction(method):
            await method(*args)
        else:
            method(*args)
    except Exception as exc:
        logger.warning("phase event failed: %s", exc)


def _exhausted_turn_budget(state: AgentState) -> bool:
    """检查是否已耗尽 turn 预算"""
    return state.get("current_turn", 0) >= state.get("max_turns", 100)


# === 辅助函数 ===


def _correction_total(state: AgentState, next_loop_count: int) -> int:
    """统计三类纠正计数合计(用 next_loop_count 覆盖即将更新的 loop_detection_count)。"""
    return (
        int(state.get("empty_retry_count", 0) or 0)
        + int(next_loop_count or 0)
        + int(state.get("stuck_detection_count", 0) or 0)
    )


# === 无效工具调用检测 ===


async def _detect_invalid_tool_calls(state: AgentState, config: RunnableConfig) -> dict | None:
    """检测无效工具调用（缺少 name 或 id）

    如果 LLM 返回的工具调用缺少必要字段（name 或 id），
    说明工具调用格式错误，需要纠正。

    Returns:
        如果检测到无效工具调用，返回状态更新字典；否则返回 None
    """
    pending_tool_calls = state.get("pending_tool_calls", [])

    if not pending_tool_calls:
        return None

    # 检查是否存在无效工具调用
    invalid_calls = [
        tc for tc in pending_tool_calls
        if not tc.get("name") or not tc.get("id")
    ]

    if not invalid_calls:
        return None

    # 检测到无效工具调用
    task_id = state.get("task_id", "")
    current_turn = state.get("current_turn", 0)
    event_emitter = _get_event_emitter(config)
    previous_phase = state.get("phase", "thinking")
    next_count = state.get("loop_detection_count", 0) + 1

    # 决定升级策略
    if next_count >= 3:
        action = "terminate"
    elif next_count == 2:
        action = "compact_context"
    else:
        action = "inject_feedback"

    # 日志
    logger.info(
        "[NODE:loop_detect] INVALID_TOOL_CALL_DETECTED | task_id=%s | turn=%d | "
        "detection_count=%d | action=%s | invalid_count=%d",
        task_id, current_turn, next_count, action, len(invalid_calls)
    )

    await _emit_safe(
        event_emitter,
        task_id,
        "loop:detected",
        {
            "loopType": "invalid_tool_call",
            "count": next_count,
            "action": action,
            "invalidCount": len(invalid_calls),
        },
    )
    await _emit_phase_safe(event_emitter, task_id, "loop_correcting", previous_phase, current_turn)

    base_update = {
        "loop_detected": True,
        "loop_detection_count": next_count,
        "loop_type": "invalid_tool_call",
        "phase": "loop_correcting",
    }

    # 升级策略处理
    correction_total = _correction_total(state, next_count)
    if next_count >= 3 or correction_total >= GLOBAL_CORRECTION_BUDGET:
        terminate_reason = (
            "invalid_tool_call_loop"
            if next_count >= 3
            else "global_correction_budget_exhausted"
        )
        logger.error(
            "[NODE:loop_detect] LOOP_TERMINATE | task_id=%s | turn=%d | "
            "detection_count=%d | correction_total=%d | reason=%s",
            task_id, current_turn, next_count, correction_total, terminate_reason,
        )
        base_update["error"] = (
            "Invalid tool calls loop, terminating after 3 attempts"
            if next_count >= 3
            else "Global correction budget exhausted"
        )
        base_update["should_end"] = True
        return base_update

    if _exhausted_turn_budget(state):
        max_turns = state.get("max_turns", 100)
        logger.error(
            "[NODE:loop_detect] BUDGET_EXHAUSTED | task_id=%s | turn=%d/%d | "
            "reason=invalid_tool_call_loop_recovery",
            task_id, current_turn, max_turns
        )
        base_update["error"] = f"Max turns ({max_turns}) reached during invalid tool call loop recovery"
        base_update["should_end"] = True
        return base_update

    if next_count == 2:
        # 上下文压缩
        logger.warning(
            "[NODE:loop_detect] CONTEXT_COMPACT_TRIGGER | task_id=%s | turn=%d | "
            "reason=invalid_tool_call_loop_detected_twice",
            task_id, current_turn
        )
        base_update["compression_strategy"] = "summarize"
        return base_update

    # count == 1: 注入格式纠正反馈
    logger.warning(
        "[NODE:loop_detect] FEEDBACK_INJECT | task_id=%s | turn=%d | "
        "reason=invalid_tool_call | correction_total=%d",
        task_id, current_turn, correction_total,
    )
    base_update["messages"] = [
        SystemMessage(
            content=(
                "[SYSTEM CORRECTION] You provided invalid tool calls with missing information. "
                "Each tool call must include a valid tool name, tool call ID, and proper input arguments. "
                "Please fix the tool call format and try again."
            )
        )
    ]
    return base_update


# === 模式循环检测 ===


def _hash_tool_args(args: dict) -> str:
    """稳定的参数哈希,支持嵌套 JSON 结构。"""
    canonical = json.dumps(args or {}, sort_keys=True,
                           ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


def _assistant_tool_calls(message) -> list:
    """从消息中提取 tool_calls 列表"""
    from langchain_core.messages import AIMessage

    if isinstance(message, dict):
        if message.get("role") == "assistant":
            return message.get("tool_calls") or []
        return []
    if isinstance(message, AIMessage):
        return message.tool_calls or []
    return []


def _detect_alternating_pattern(recent_tool_calls: list) -> tuple[bool, str | None]:
    """检测 A-B-A-B 交替模式

    例如：read_file(A) → grep_search(B) → read_file(A) → grep_search(B)

    Args:
        recent_tool_calls: 最近 4 轮工具调用签名列表 [(name, arg_hash), ...]

    Returns:
        (是否检测到交替模式, 模式类型)
    """
    if len(recent_tool_calls) < 4:
        return False, None

    # 提取最近 4 轮工具调用签名
    sig_1 = recent_tool_calls[3]  # 最远
    sig_2 = recent_tool_calls[2]
    sig_3 = recent_tool_calls[1]
    sig_4 = recent_tool_calls[0]  # 最近

    # 检查是否 A-B-A-B 模式: sig_4==sig_2, sig_3==sig_1, sig_4!=sig_3
    if sig_4 == sig_2 and sig_3 == sig_1 and sig_4 != sig_3:
        return True, "alternating_pattern"

    return False, None


async def _detect_pattern_loop(state: AgentState, config: RunnableConfig) -> dict:
    """检测工具调用模式重复(精确匹配 + A-B-A-B 交替)"""
    start_index = state.get("task_start_message_count", 0)
    messages = state["messages"][start_index:]
    threshold = 3  # 连续重复阈值
    window = 5  # 检测窗口

    # 提取最近的工具调用
    recent_tool_calls = []
    for msg in reversed(messages):
        tool_calls = _assistant_tool_calls(msg)
        if tool_calls:
            recent_tool_calls.append(tool_calls)
            if len(recent_tool_calls) >= window:
                break

    # 精确匹配检测
    loop_detected = False
    loop_type = None

    if len(recent_tool_calls) >= threshold:
        signatures = []
        for tc_list in recent_tool_calls[:threshold]:
            if not tc_list:
                break
            sig = tuple(
                (
                    tc.get("name"),
                    _hash_tool_args(
                        tc.get("args") or tc.get("arguments") or {}),
                )
                for tc in tc_list
            )
            signatures.append(sig)

        if len(signatures) == threshold and len(set(signatures)) == 1:
            loop_detected = True
            loop_type = "exact_tool_repeat"

    # A-B-A-B 交替检测
    if not loop_detected:
        # 提取最近 4 轮工具调用签名
        recent_signatures = []
        for tc_list in recent_tool_calls[:4]:
            if not tc_list:
                break
            # 简化：只取第一个工具调用的签名
            tc = tc_list[0]
            sig = (tc.get("name"), _hash_tool_args(
                tc.get("args") or tc.get("arguments") or {}))
            recent_signatures.append(sig)

        if len(recent_signatures) >= 4:
            is_alternating, alt_type = _detect_alternating_pattern(
                recent_signatures)
            if is_alternating:
                loop_detected = True
                loop_type = alt_type

    if not loop_detected:
        return {"loop_detected": False, "loop_type": None, "loop_detection_count": 0}

    # === Loop 检测到:内部处理反馈与升级策略 ===
    event_emitter = _get_event_emitter(config)
    current_turn = state.get("current_turn", 0)
    previous_phase = state.get("phase", "thinking")
    next_count = state.get("loop_detection_count", 0) + 1

    # 决定升级策略
    if next_count >= 3:
        action = "terminate"
    elif next_count == 2:
        action = "compact_context"
    else:
        action = "inject_feedback"

    # 模式循环检测日志
    logger.info(
        "[NODE:loop_detect] PATTERN_LOOP_DETECTED | task_id=%s | turn=%d | "
        "loop_type=%s | detection_count=%d | action=%s",
        state.get("task_id", ""), current_turn, loop_type, next_count, action
    )

    await _emit_safe(
        event_emitter,
        state["task_id"],
        "loop:detected",
        {
            "loopType": loop_type,
            "count": next_count,
            "action": action,
        },
    )
    await _emit_phase_safe(event_emitter, state["task_id"], "loop_correcting", previous_phase, current_turn)

    base_update = {
        "loop_detected": True,
        "loop_detection_count": next_count,
        "loop_type": loop_type,
        "phase": "loop_correcting",
    }

    # 升级策略处理
    correction_total = _correction_total(state, next_count)
    if next_count >= 3 or correction_total >= GLOBAL_CORRECTION_BUDGET:
        terminate_reason = (
            "pattern_loop" if next_count >= 3 else "global_correction_budget_exhausted"
        )
        logger.error(
            "[NODE:loop_detect] LOOP_TERMINATE | task_id=%s | turn=%d | "
            "detection_count=%d | correction_total=%d | loop_type=%s | reason=%s",
            state.get("task_id", ""), current_turn, next_count,
            correction_total, loop_type, terminate_reason,
        )
        base_update["error"] = (
            "Loop detected, terminating after 3 attempts"
            if next_count >= 3
            else "Global correction budget exhausted"
        )
        base_update["should_end"] = True
        return base_update

    if _exhausted_turn_budget(state):
        # 预算耗尽
        max_turns = state.get("max_turns", 100)
        logger.error(
            "[NODE:loop_detect] BUDGET_EXHAUSTED | task_id=%s | turn=%d/%d | "
            "reason=pattern_loop_recovery",
            state.get("task_id", ""), current_turn, max_turns
        )
        base_update["error"] = f"Max turns ({max_turns}) reached during loop recovery"
        base_update["should_end"] = True
        return base_update

    if next_count == 2:
        # 上下文压缩:设置压缩策略,路由到 context_compact
        logger.warning(
            "[NODE:loop_detect] CONTEXT_COMPACT_TRIGGER | task_id=%s | turn=%d | "
            "reason=pattern_loop_detected_twice | loop_type=%s",
            state.get("task_id", ""), current_turn, loop_type
        )
        base_update["compression_strategy"] = "summarize"
        return base_update

    # count == 1: 注入反馈
    logger.warning(
        "[NODE:loop_detect] FEEDBACK_INJECT | task_id=%s | turn=%d | "
        "loop_type=%s | correction_total=%d",
        state.get("task_id", ""), current_turn, loop_type, correction_total,
    )
    base_update["messages"] = [
        SystemMessage(
            content=(
                "[SYSTEM CORRECTION] You seem to be repeating the same actions. "
                "Please try a different approach to solve the task. "
                "Analyze what went wrong and propose a new strategy."
            )
        )
    ]
    return base_update


# === 节点入口 ===


class LoopDetectNode(BaseNode):
    """Loop 检测节点(前置拦截)"""

    @property
    def node_name(self) -> str:
        return "loop_detect"

    @property
    def default_phase(self) -> str | None:
        return None  # 此节点内部自行控制 phase

    async def execute(self, state: AgentState, config: RunnableConfig, context: NodeContext) -> dict:
        """执行 Loop 检测

        检测策略(按优先级):
        1. 无效工具调用检测(INVALID_TOOL_CALL)
        2. 精确匹配检测(EXACT_TOOL_REPEAT)
        3. A-B-A-B 交替检测(ALTERNATING_PATTERN)

        Args:
            state: 当前 Agent 状态
            config: LangGraph 配置
            context: 节点执行上下文

        Returns:
            状态更新字典 (包含 loop_detected、反馈消息等)
        """
        # 步骤1: 检测无效工具调用
        invalid_result = await _detect_invalid_tool_calls(state, config)
        if invalid_result:
            return invalid_result

        # 步骤2: 检测模式循环(精确匹配 + ABAB 交替)
        pattern_result = await _detect_pattern_loop(state, config)
        return pattern_result


# 保持向后兼容的实例导出
loop_detect_node = LoopDetectNode()
