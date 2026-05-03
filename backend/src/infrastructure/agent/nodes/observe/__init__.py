"""Observe 节点共享工具函数包

供 observe_answer_node / observe_tool_node / loop_detect_node / stuck_detect_node 使用的
共享工具函数和常量。
"""

from __future__ import annotations

import inspect
import logging
from typing import Any, Dict, List

from langgraph.types import RunnableConfig

from src.domain.entities.agent_state import AgentState

logger = logging.getLogger(__name__)

# === 常量 ===

_DEFAULT_EMPTY_THRESHOLD_CHARS = 2
_DEFAULT_MAX_CONSECUTIVE_EMPTY = 2
_EMPTY_PLACEHOLDERS = {"", "[]", "{}", "null", "none", "no result"}

# === 消息提取工具 ===


def extract_text(msg: Any) -> str:
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


# === 判定工具 ===


def exhausted_turn_budget(state: dict) -> bool:
    """当前响应已消耗最后一个 LLM turn，无法再继续下一轮。"""
    return state.get("current_turn", 0) >= state.get("max_turns", 100)


def get_option(config: RunnableConfig, key: str, default: Any) -> Any:
    opts = (config.get("configurable") or {}).get("observe_options") or {}
    return opts.get(key, default)


def is_empty_output(output: Any, threshold: int) -> bool:
    if output is None:
        return True
    text = output if isinstance(output, str) else str(output)
    stripped = text.strip()
    if len(stripped) <= threshold:
        return True
    if stripped.lower() in _EMPTY_PLACEHOLDERS:
        return True
    return False


def judge_quality(result: Dict[str, Any], empty_threshold: int) -> str:
    status = result.get("status")
    if status == "skipped":
        return "skipped"
    if status == "error":
        return "failed"
    if status != "success":
        return "failed"

    if is_empty_output(result.get("output"), empty_threshold):
        return "empty"

    return "good"


def aggregate_quality(items: List[Dict[str, Any]]) -> str:
    qualities = {i["quality"] for i in items if i["quality"] != "skipped"}
    if not qualities:
        return "good"
    if qualities == {"good"}:
        return "good"
    if qualities == {"empty"}:
        return "empty"
    if qualities == {"failed"}:
        return "failed"
    return "mixed"


# === 事件发射 ===


async def emit_safe(emitter: Any, *args: Any, **kwargs: Any) -> None:
    if emitter is None:
        return
    try:
        method = emitter.emit
        if inspect.iscoroutinefunction(method):
            await method(*args, **kwargs)
        else:
            method(*args, **kwargs)
    except Exception as exc:
        logger.warning("observe event emit failed: %s", exc)


async def emit_phase_safe(emitter: Any, *args: Any) -> None:
    if emitter is None:
        return
    try:
        method = emitter.emit_phase_changed
        if inspect.iscoroutinefunction(method):
            await method(*args)
        else:
            method(*args)
    except Exception as exc:
        logger.warning("observe phase event failed: %s", exc)


def get_event_emitter(config: RunnableConfig) -> Any:
    return (config.get("configurable") or {}).get("event_emitter") or (
        config.get("configurable") or {}
    ).get("event_service")


async def emit_decision(
    event_emitter: Any,
    task_id: str,
    current_turn: int,
    route_hint: str,
    reason: str,
) -> None:
    await emit_safe(
        event_emitter,
        task_id,
        "observe:decision",
        {
            "turn": current_turn,
            "routeHint": route_hint,
            "reason": reason,
        },
    )


# === 结果提取与状态更新 ===


def extract_final_result(state: AgentState) -> str:
    if state.get("final_result"):
        return state["final_result"]
    messages = state.get("messages", [])
    if messages:
        return extract_text(messages[-1])
    return ""


def mode_c_update(
    route_hint: str,
    observation_quality: str,
    *,
    empty_retry_count: int = 0,
    planning_retry_count: int = 0,
    phase: str = "evaluating",
    **extra: Any,
) -> dict:
    update = {
        "empty_retry_count": empty_retry_count,
        "planning_retry_count": planning_retry_count,
        "route_hint": route_hint,
        "observe_mode": "llm_output",
        "observation_quality": observation_quality,
        "phase": phase,
    }
    update.update(extra)
    return update


__all__ = [
    "_DEFAULT_EMPTY_THRESHOLD_CHARS",
    "_DEFAULT_MAX_CONSECUTIVE_EMPTY",
    "aggregate_quality",
    "emit_decision",
    "emit_phase_safe",
    "emit_safe",
    "exhausted_turn_budget",
    "extract_final_result",
    "extract_text",
    "get_event_emitter",
    "get_option",
    "is_empty_output",
    "judge_quality",
    "mode_c_update",
]
