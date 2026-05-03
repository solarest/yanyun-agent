"""基础设施层 - Loop 检测节点(增强版)

LangGraph Node: loop_detect_node
职责:
1. 评估工具执行结果质量(新增,原 tool_observe 职责)
2. 检测工具连续空结果(质量循环)
3. 检测工具调用模式重复(精确匹配 + 内容相似度)
4. 内部处理反馈注入与升级策略(吸收原 loop_feedback_node)
5. 预算耗尽检查
"""

import hashlib
import json
import logging
import re
from collections import Counter
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.types import RunnableConfig

from src.domain.entities.agent_state import AgentState
from src.infrastructure.agent.nodes.observe import (
    _DEFAULT_EMPTY_THRESHOLD_CHARS,
    _DEFAULT_MAX_CONSECUTIVE_EMPTY,
    aggregate_quality,
    emit_decision,
    emit_phase_safe,
    emit_safe,
    exhausted_turn_budget,
    extract_final_result,
    get_event_emitter,
    get_option,
    judge_quality,
)

logger = logging.getLogger(__name__)

# 全局纠正预算:空响应/循环/卡住计数累计达到此阈值即终止
GLOBAL_CORRECTION_BUDGET = 3

# === 工具结果评估(原 tool_observe 职责) ===


def _classify_error(error: str) -> str:
    """根据错误消息分类错误类型(规则判断)

    分类规则:
    - permission: 包含 "permission denied"/"unauthorized"/"access denied"
    - timeout: 包含 "timeout"/"timed out"
    - not_found: 包含 "not found"/"does not exist"/"no such file"
    - network: 包含 "connection refused"/"network error"/"connection error"
    - invalid_args: 包含 "invalid argument"/"parameter error"/"invalid parameter"
    - business_error: 包含业务错误关键词
    - unknown: 其他错误
    """
    if not error:
        return "unknown"

    error_lower = error.lower()

    # 权限错误(致命)
    if any(kw in error_lower for kw in ["permission denied", "unauthorized", "access denied", "forbidden"]):
        return "permission"

    # 超时错误
    if any(kw in error_lower for kw in ["timeout", "timed out"]):
        return "timeout"

    # 未找到错误
    if any(kw in error_lower for kw in ["not found", "does not exist", "no such file", "file not found"]):
        return "not_found"

    # 网络错误
    if any(kw in error_lower for kw in ["connection refused", "network error", "connection error", "dns resolution"]):
        return "network"

    # 参数错误
    if any(kw in error_lower for kw in ["invalid argument", "parameter error", "invalid parameter", "missing required"]):
        return "invalid_args"

    # 业务错误(包含 error/failed 等)
    if any(kw in error_lower for kw in ["error", "failed", "failure"]):
        return "business_error"

    return "unknown"


async def _evaluate_tool_results(state: AgentState, config: RunnableConfig) -> dict:
    """评估工具执行结果质量(规则判断)

    质量判定规则:
    - good: status=success 且输出非空(>阈值字符)
    - empty: status=success 但输出为空/占位
    - failed: status=error
    - skipped: status=skipped(不计入统计)

    Returns:
        状态更新字典,包含 observation_summary/observation_quality/observation_items 等
    """
    executed_ids: List[str] = list(
        state.get("last_executed_tool_call_ids", []) or [])
    tool_results: Dict[str, Dict[str, Any]] = state.get(
        "tool_results", {}) or {}
    task_id = state.get("task_id", "")
    current_turn = state.get("current_turn", 0)

    if not executed_ids:
        return {}

    empty_threshold = int(get_option(
        config, "empty_threshold_chars", _DEFAULT_EMPTY_THRESHOLD_CHARS))

    # 规则判断质量
    items: List[Dict[str, Any]] = []
    for tool_call_id in executed_ids:
        result = tool_results.get(tool_call_id)
        if not result:
            continue

        try:
            quality = judge_quality(result, empty_threshold)
            if quality == "skipped":
                continue

            item = {
                "toolCallId": tool_call_id,
                "toolName": result.get("tool_name", ""),
                "quality": quality,
                "errorCategory": None,
            }

            # 错误分类
            if quality == "failed":
                error = result.get("error", "")
                item["errorCategory"] = _classify_error(error)

            items.append(item)
        except Exception:
            logger.exception(
                "loop detect: tool quality parse failed: %s", tool_call_id)
            items.append({
                "toolCallId": tool_call_id,
                "toolName": result.get("tool_name", ""),
                "quality": "failed",
                "errorCategory": "unknown",
            })

    if not items:
        return {}

    # 聚合质量
    overall_quality = aggregate_quality(items)
    has_fatal = any(i["errorCategory"] == "permission" for i in items)
    last_error_category: Optional[str] = None
    for item in reversed(items):
        if item.get("errorCategory"):
            last_error_category = item["errorCategory"]
            break

    # 生成摘要
    parts = [f"{i['toolName']}:{i['quality']}" for i in items]
    observation_summary = f"[{overall_quality}] " + ", ".join(parts)

    # 事件发射
    event_emitter = get_event_emitter(config)
    await emit_safe(
        event_emitter,
        task_id,
        "observe:summary",
        {
            "turn": current_turn,
            "items": items,
            "overallQuality": overall_quality,
        },
    )

    # 日志
    logger.info(
        "[NODE:loop_detect] TOOL_RESULT_EVAL | task_id=%s | turn=%d | "
        "quality=%s | items_count=%d | has_fatal=%s",
        task_id, current_turn, overall_quality, len(items), has_fatal
    )

    update = {
        "observation_summary": observation_summary,
        "observation_quality": overall_quality,
        "observation_items": items,
        "last_error_category": last_error_category,
        "last_executed_tool_call_ids": [],  # 消费后清空
    }

    # 致命错误直接终止
    if has_fatal:
        await emit_decision(event_emitter, task_id, current_turn, "terminate", f"fatal_error:{last_error_category}")
        update["should_end"] = True
        update["error"] = f"Fatal tool error: {last_error_category}"
        update["final_result"] = extract_final_result(state)
        update["route_hint"] = "terminate"

    return update


# === 循环检测逻辑 ===


def _correction_total(state: AgentState, next_loop_count: int) -> int:
    """统计三类纠正计数合计(用 next_loop_count 覆盖即将更新的 loop_detection_count)。"""
    return (
        int(state.get("empty_retry_count", 0) or 0)
        + int(next_loop_count or 0)
        + int(state.get("stuck_detection_count", 0) or 0)
    )


async def _detect_empty_tool_loop(state: AgentState, config: RunnableConfig) -> dict | None:
    """检测工具连续空结果(质量循环)。

    如果工具连续多次返回空结果,说明 LLM 可能在循环调用无效工具。

    Returns:
        如果检测到空结果循环,返回状态更新字典;否则返回 None
    """
    executed_ids: List[str] = list(
        state.get("last_executed_tool_call_ids", []) or [])
    tool_results: Dict[str, Dict[str, Any]] = state.get(
        "tool_results", {}) or {}
    task_id = state.get("task_id", "")
    current_turn = state.get("current_turn", 0)

    if not executed_ids:
        return None

    empty_threshold = int(get_option(
        config, "empty_threshold_chars", _DEFAULT_EMPTY_THRESHOLD_CHARS))
    max_consec_empty = int(get_option(
        config, "max_consecutive_empty", _DEFAULT_MAX_CONSECUTIVE_EMPTY))

    # 评估当前工具结果质量
    items = []
    for tool_call_id in executed_ids:
        result = tool_results.get(tool_call_id)
        if not result:
            continue
        try:
            quality = judge_quality(result, empty_threshold)
            if quality == "skipped":
                continue
            items.append({
                "toolCallId": tool_call_id,
                "toolName": result.get("tool_name", ""),
                "quality": quality,
            })
        except Exception:
            logger.exception(
                "loop detect: tool quality parse failed: %s", tool_call_id)
            items.append({
                "toolCallId": tool_call_id,
                "toolName": result.get("tool_name", ""),
                "quality": "failed",
            })

    overall_quality = aggregate_quality(items)

    # 只有空结果才计入循环检测
    if overall_quality != "empty":
        return None

    prev_empty_count = int(state.get("consecutive_empty_observations", 0) or 0)
    consecutive_empty = prev_empty_count + 1

    # 空结果计数日志
    logger.info(
        "[NODE:loop_detect] EMPTY_RESULT_CHECK | task_id=%s | turn=%d | "
        "overall_quality=%s | consecutive_empty=%d/%d",
        task_id, current_turn, overall_quality, consecutive_empty, max_consec_empty
    )

    if consecutive_empty < max_consec_empty:
        # 未达到阈值,更新计数但不触发循环处理
        return {
            "consecutive_empty_observations": consecutive_empty,
            "loop_detected": False,
            "loop_type": None,
            "loop_detection_count": 0,
        }

    # 达到阈值,触发循环处理
    event_emitter = get_event_emitter(config)
    previous_phase = state.get("phase", "tool_executing")
    next_count = state.get("loop_detection_count", 0) + 1

    # 决定升级策略
    if next_count >= 3:
        action = "terminate"
    elif next_count == 2:
        action = "compact_context"
    else:
        action = "inject_feedback"

    # 循环检测日志
    logger.info(
        "[NODE:loop_detect] EMPTY_LOOP_DETECTED | task_id=%s | turn=%d | "
        "detection_count=%d | action=%s | consecutive_empty=%d",
        task_id, current_turn, next_count, action, consecutive_empty
    )

    await event_emitter.emit(
        state["task_id"],
        "loop:detected",
        {
            "loopType": "empty_tool_result",
            "count": next_count,
            "action": action,
            "consecutiveEmpty": consecutive_empty,
        },
    )
    await emit_phase_safe(event_emitter, state["task_id"], "loop_correcting", previous_phase, current_turn)

    base_update = {
        "loop_detected": True,
        "loop_detection_count": next_count,
        "loop_type": "empty_tool_result",
        "consecutive_empty_observations": consecutive_empty,
        "phase": "loop_correcting",
        "route_hint": "llm_call" if next_count < 3 else "terminate",
    }

    # 升级策略终止判定:原单项计数或全局熔断
    correction_total = _correction_total(state, next_count)
    if next_count >= 3 or correction_total >= GLOBAL_CORRECTION_BUDGET:
        terminate_reason = (
            "empty_tool_result_loop"
            if next_count >= 3
            else "global_correction_budget_exhausted"
        )
        logger.error(
            "[NODE:loop_detect] LOOP_TERMINATE | task_id=%s | turn=%d | "
            "detection_count=%d | correction_total=%d | reason=%s",
            task_id, current_turn, next_count, correction_total, terminate_reason,
        )
        base_update["error"] = (
            "Empty tool results loop, terminating after 3 attempts"
            if next_count >= 3
            else "Global correction budget exhausted"
        )
        base_update["should_end"] = True
        base_update["route_hint"] = "terminate"
        return base_update

    if exhausted_turn_budget(state):
        max_turns = state.get("max_turns", 100)
        logger.error(
            "[NODE:loop_detect] BUDGET_EXHAUSTED | task_id=%s | turn=%d/%d | "
            "reason=empty_result_loop_recovery",
            task_id, current_turn, max_turns
        )
        base_update["error"] = f"Max turns ({max_turns}) reached during empty result loop recovery"
        base_update["should_end"] = True
        base_update["route_hint"] = "terminate"
        return base_update

    if next_count == 2:
        logger.warning(
            "[NODE:loop_detect] CONTEXT_COMPACT_TRIGGER | task_id=%s | turn=%d | "
            "reason=empty_result_loop_detected_twice",
            task_id, current_turn
        )
        base_update["compression_strategy"] = "summarize"
        base_update["route_hint"] = "context_compact"
        return base_update

    # count == 1: 注入反馈
    logger.warning(
        "[NODE:loop_detect] FEEDBACK_INJECT | task_id=%s | turn=%d | "
        "reason=empty_tool_result_loop | correction_total=%d",
        task_id, current_turn, correction_total,
    )
    base_update["messages"] = [
        SystemMessage(
            content=(
                "[SYSTEM CORRECTION] Your recent tool calls produced no useful output. "
                "Please analyze why the tools are returning empty results "
                "and try a different approach or tool."
            )
        )
    ]
    return base_update


async def _detect_pattern_loop(state: AgentState, config: RunnableConfig) -> dict:
    """检测工具调用模式重复(精确匹配 + 内容相似度)。"""
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

    # 内容相似度检测:仅在纯文本轮次(无 tool_calls)生效,避免对并行多 tool_call 场景的误判
    if not loop_detected:
        assistant_entries: list[tuple[str, list]] = []
        for msg in reversed(messages):
            text = _assistant_text(msg)
            tool_calls = _assistant_tool_calls(msg)
            if text or tool_calls:
                assistant_entries.append((text, tool_calls))
                if len(assistant_entries) >= 4:
                    break

        # 只有窗口内所有 assistant 消息都无 tool_calls 且均有文本时,才启用 Jaccard 判定
        assistant_texts = [t for t, _ in assistant_entries]
        has_any_tool_calls = any(tc for _, tc in assistant_entries)
        if (
            not has_any_tool_calls
            and len(assistant_texts) >= 2
            and all(t for t in assistant_texts)
        ):
            similarities = []
            for i in range(len(assistant_texts) - 1):
                words1 = Counter(assistant_texts[i].split())
                words2 = Counter(assistant_texts[i + 1].split())
                intersection = sum((words1 & words2).values())
                union = sum((words1 | words2).values())
                sim = intersection / union if union > 0 else 0
                similarities.append(sim)

            if similarities and all(s > 0.92 for s in similarities):
                loop_detected = True
                loop_type = "content_repeat"

    if not loop_detected:
        return {"loop_detected": False, "loop_type": None, "loop_detection_count": 0, "route_hint": "llm_call"}

    # === Loop 检测到:内部处理反馈与升级策略 ===
    event_emitter = get_event_emitter(config)
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

    await event_emitter.emit(
        state["task_id"],
        "loop:detected",
        {
            "loopType": loop_type,
            "count": next_count,
            "action": action,
        },
    )
    await emit_phase_safe(event_emitter, state["task_id"], "loop_correcting", previous_phase, current_turn)

    base_update = {
        "loop_detected": True,
        "loop_detection_count": next_count,
        "loop_type": loop_type,
        "phase": "loop_correcting",
        "route_hint": "llm_call" if next_count < 3 else "terminate",
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
        base_update["route_hint"] = "terminate"
        return base_update

    if exhausted_turn_budget(state):
        # 预算耗尽
        max_turns = state.get("max_turns", 100)
        logger.error(
            "[NODE:loop_detect] BUDGET_EXHAUSTED | task_id=%s | turn=%d/%d | "
            "reason=pattern_loop_recovery",
            state.get("task_id", ""), current_turn, max_turns
        )
        base_update["error"] = f"Max turns ({max_turns}) reached during loop recovery"
        base_update["should_end"] = True
        base_update["route_hint"] = "terminate"
        return base_update

    if next_count == 2:
        # 上下文压缩:设置压缩策略,路由到 context_compact
        logger.warning(
            "[NODE:loop_detect] CONTEXT_COMPACT_TRIGGER | task_id=%s | turn=%d | "
            "reason=pattern_loop_detected_twice | loop_type=%s",
            state.get("task_id", ""), current_turn, loop_type
        )
        base_update["compression_strategy"] = "summarize"
        base_update["route_hint"] = "context_compact"
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


def _assistant_tool_calls(message) -> list:
    if isinstance(message, dict):
        if message.get("role") == "assistant":
            return message.get("tool_calls") or []
        return []
    if isinstance(message, AIMessage):
        return message.tool_calls or []
    return []


def _assistant_text(message) -> str:
    if isinstance(message, dict):
        if message.get("role") == "assistant":
            return message.get("content", "") or ""
        return ""
    if isinstance(message, AIMessage):
        return message.content or ""
    return ""


def _hash_tool_args(args: dict) -> str:
    """稳定的参数哈希,支持嵌套 JSON 结构。"""
    canonical = json.dumps(args or {}, sort_keys=True,
                           ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


async def loop_detect_node(state: AgentState, config: RunnableConfig) -> dict:
    """Loop 检测节点(增强版)

    检测策略:
    1. 评估工具结果质量(新增,原 tool_observe 职责)
    2. 检测工具连续空结果(质量循环)
    3. 检测工具调用模式重复(精确匹配 + 内容相似度)

    内部升级策略(吸收 loop_feedback_node):
    - count 1: 注入警告反馈 → 路由回 llm_call
    - count 2: 设置 compression_strategy → 路由到 context_compact
    - count >= 3: 终止

    Args:
        state: 当前 Agent 状态
        config: LangGraph 配置

    Returns:
        状态更新字典 (包含 loop_detected、反馈消息等)
    """
    # 步骤1: 评估工具结果质量(如果有刚执行的工具)
    executed_ids: List[str] = list(
        state.get("last_executed_tool_call_ids", []) or [])
    quality_update = {}
    if executed_ids:
        quality_update = await _evaluate_tool_results(state, config)

    # 步骤2: 检测质量循环(工具连续空结果)
    empty_loop_result = await _detect_empty_tool_loop(state, config)
    if empty_loop_result:
        return {**quality_update, **empty_loop_result}

    # 步骤3: 检测模式循环(精确匹配 + 内容相似度)
    pattern_loop_result = await _detect_pattern_loop(state, config)

    return {**quality_update, **pattern_loop_result}
