"""基础设施层 - Observation 节点

LangGraph Node: observe_node
职责：ReAct 闭环中的"观察"环节。对工具结果做质量判定、错误分类、
     摘要化、反思注入，并给出路由建议。

设计文档：design/1.5_observe-node-design.md
"""

from __future__ import annotations

import inspect
import logging
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.messages import HumanMessage
from langgraph.types import RunnableConfig

from src.domain.entities.agent_state import AgentState

logger = logging.getLogger(__name__)


# === 默认配置 ===

_DEFAULT_EMPTY_THRESHOLD_CHARS = 2
_DEFAULT_MAX_CONSECUTIVE_EMPTY = 2
_REFLECTION_MAX_CHARS = 500

# 输出被视为"空"的典型占位
_EMPTY_PLACEHOLDERS = {"", "[]", "{}", "null", "none", "no result"}


def _get_option(config: RunnableConfig, key: str, default: Any) -> Any:
    opts = (config.get("configurable") or {}).get("observe_options") or {}
    return opts.get(key, default)


# === 错误分类 ===

_ERROR_RULES: List[Tuple[str, Tuple[str, ...]]] = [
    ("timeout", ("timed out", "timeout", "deadline exceeded")),
    ("permission", ("permission denied", "unauthorized", "forbidden", "access denied")),
    ("invalid_args", ("validationerror", "invalid argument", "missing required", "invalid parameter")),
    ("not_found", ("not found", "does not exist", "no such file")),
    ("network", ("connection", "network", "dns", "unreachable", "ssl")),
]


def _classify_error(error_text: Optional[str], metadata: Dict[str, Any]) -> str:
    """将工具错误字符串映射到有限的错误类别"""
    # metadata 明示优先
    explicit = (metadata or {}).get("error_type")
    if isinstance(explicit, str) and explicit:
        return explicit

    if not error_text:
        return "unknown"

    lower = error_text.lower()
    for category, keywords in _ERROR_RULES:
        if any(kw in lower for kw in keywords):
            return category
    return "unknown"


# === 质量判定 ===

def _is_empty_output(output: Any, threshold: int) -> bool:
    if output is None:
        return True
    text = output if isinstance(output, str) else str(output)
    stripped = text.strip()
    if len(stripped) <= threshold:
        return True
    if stripped.lower() in _EMPTY_PLACEHOLDERS:
        return True
    return False


def _judge_quality(
    result: Dict[str, Any],
    empty_threshold: int,
) -> str:
    """返回质量判定结果"""
    status = result.get("status")
    metadata = result.get("metadata") or {}

    if status == "skipped":
        return "skipped"
    if status == "error":
        return "failed"
    if status != "success":
        return "failed"

    if _is_empty_output(result.get("output"), empty_threshold):
        return "empty"

    return "good"


# === 反思文本 ===

_REFLECTION_TEMPLATES = {
    "empty": (
        "Observed: tool '{tool}' returned an empty result. "
        "Consider refining parameters or trying a different approach."
    ),
    "failed_timeout": (
        "Observed: tool '{tool}' timed out. You may retry once or switch strategy."
    ),
    "failed_permission": (
        "Observed: tool '{tool}' was denied by permission. "
        "Do not retry; inform the user or choose a different tool."
    ),
    "failed_invalid_args": (
        "Observed: tool '{tool}' rejected the arguments. Fix parameters before retrying."
    ),
    "failed_not_found": (
        "Observed: tool '{tool}' target not found. Verify the identifier or switch target."
    ),
    "failed_network": (
        "Observed: tool '{tool}' encountered a network error. Retry may help."
    ),
    "failed_business_error": (
        "Observed: tool '{tool}' raised a business error. Review the error and adjust approach."
    ),
    "failed_unknown": (
        "Observed: tool '{tool}' failed with an unknown error. Consider alternative approaches."
    ),
    "multi_success": (
        "Observed: {count} tools succeeded. Proceed to the next step."
    ),
}


def _build_reflection(
    items: List[Dict[str, Any]],
    overall_quality: str,
) -> Optional[str]:
    """根据观察项生成反思文本。返回 None 表示无需注入。"""
    if not items:
        return None

    success_items = [i for i in items if i["quality"] == "good"]

    # 单工具成功：保持原有行为，不注入
    if overall_quality == "good" and len(items) == 1:
        return None

    # 多工具全部成功：轻量提示
    if overall_quality == "good" and len(success_items) == len(items):
        return _REFLECTION_TEMPLATES["multi_success"].format(count=len(items))

    # 选取第一条非 good 条目作为主反思对象
    focus = next((i for i in items if i["quality"] != "good"), items[0])
    tool = focus.get("toolName") or "<unknown>"
    quality = focus["quality"]

    if quality == "empty":
        text = _REFLECTION_TEMPLATES["empty"].format(tool=tool)
    elif quality == "failed":
        key = f"failed_{focus.get('errorCategory') or 'unknown'}"
        tpl = _REFLECTION_TEMPLATES.get(key, _REFLECTION_TEMPLATES["failed_unknown"])
        text = tpl.format(tool=tool)
    else:
        return None

    if len(text) > _REFLECTION_MAX_CHARS:
        text = text[: _REFLECTION_MAX_CHARS - 3] + "..."
    return text


# === 整体质量聚合 ===

def _aggregate_quality(items: List[Dict[str, Any]]) -> str:
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


# === 致命错误判断 ===

_FATAL_CATEGORIES = {"permission"}


def _has_fatal_error(items: List[Dict[str, Any]]) -> bool:
    return any(
        i["quality"] == "failed" and i.get("errorCategory") in _FATAL_CATEGORIES
        for i in items
    )


# === 主入口 ===

async def observe_node(state: AgentState, config: RunnableConfig) -> dict:
    """Observation 节点 — ReAct 闭环中的观察环节

    职责：
    1. 对工具结果做质量判定、错误分类、摘要化、反思注入
    2. 对 LLM 完成声明进行质量评估（无工具调用时）

    Returns:
        状态更新字典，包含 messages / observation_* / route_hint 等
    """
    event_emitter = (
        (config.get("configurable") or {}).get("event_emitter")
        or (config.get("configurable") or {}).get("event_service")
    )
    task_id = state.get("task_id", "")
    current_turn = state.get("current_turn", 0)
    previous_phase = state.get("phase", "tool_executing")

    tool_results: Dict[str, Dict[str, Any]] = state.get("tool_results", {}) or {}
    executed_ids: List[str] = list(state.get("last_executed_tool_call_ids", []) or [])

    # === 场景 A：无工具执行（LLM 声明完成） ===
    if not executed_ids:
        return await _evaluate_completion(state, event_emitter, task_id, current_turn, previous_phase)

    # === 场景 B：有工具执行（原有逻辑） ===
    # 读取配置
    empty_threshold = int(
        _get_option(config, "empty_threshold_chars", _DEFAULT_EMPTY_THRESHOLD_CHARS)
    )
    max_consec_empty = int(
        _get_option(config, "max_consecutive_empty", _DEFAULT_MAX_CONSECUTIVE_EMPTY)
    )
    enable_inject = bool(_get_option(config, "enable_reflection_inject", True))

    # 发射阶段变更事件（容错）
    if event_emitter is not None:
        try:
            await event_emitter.emit_phase_changed(
                task_id, "observing", previous_phase, current_turn,
            )
        except Exception as exc:  # pragma: no cover - 防御性
            logger.warning("observe phase event failed: %s", exc)

    # 遍历每条执行过的工具结果
    items: List[Dict[str, Any]] = []
    last_error_category: Optional[str] = None

    for tool_call_id in executed_ids:
        result = tool_results.get(tool_call_id)
        if not result:
            continue
        try:
            quality = _judge_quality(result, empty_threshold)
            if quality == "skipped":
                # Plan 分派跳过的工具不计入观察
                continue

            error_category: Optional[str] = None
            if quality == "failed":
                error_category = _classify_error(
                    result.get("error"), result.get("metadata") or {}
                )
                last_error_category = error_category

            items.append({
                "toolCallId": tool_call_id,
                "toolName": result.get("tool_name", ""),
                "quality": quality,
                "errorCategory": error_category,
            })
        except Exception:
            logger.exception("observe item parse failed: %s", tool_call_id)
            items.append({
                "toolCallId": tool_call_id,
                "toolName": result.get("tool_name", ""),
                "quality": "failed",
                "errorCategory": "unknown",
            })

    overall_quality = _aggregate_quality(items)

    # 空观察连续计数
    prev_empty_count = int(state.get("consecutive_empty_observations", 0) or 0)
    if overall_quality == "empty":
        consecutive_empty = prev_empty_count + 1
    else:
        consecutive_empty = 0

    # 决定路由建议
    # 所有 loop 的完成都必须通过 observe 显式确认
    if _has_fatal_error(items):
        # 致命错误：终止
        route_hint = "finalize"
        reason = f"fatal_error:{last_error_category}"
    elif consecutive_empty >= max_consec_empty:
        # 连续空观察：检测到循环
        route_hint = "loop_detect"
        reason = f"consecutive_empty:{consecutive_empty}"
    else:
        # 正常情况：回到 LLM 继续
        route_hint = "llm_call"
        reason = overall_quality

    # 构建反思消息
    messages: List[Any] = []
    reflection_text: Optional[str] = None
    if enable_inject and items:
        # 连续空观察时，仅首轮注入反思，避免重复轰炸
        if overall_quality == "empty" and prev_empty_count >= 1:
            reflection_text = None
        else:
            reflection_text = _build_reflection(items, overall_quality)
        if reflection_text:
            messages.append(HumanMessage(content=reflection_text))

    # 构建 summary 文本（供调试/前端）
    parts = [f"{i['toolName']}:{i['quality']}" for i in items]
    observation_summary = (
        reflection_text
        if reflection_text
        else (f"[{overall_quality}] " + ", ".join(parts) if parts else None)
    )

    # 发射事件（容错）
    if event_emitter is not None:
        try:
            await event_emitter.emit(
                task_id,
                "observe:summary",
                {
                    "turn": current_turn,
                    "items": items,
                    "overallQuality": overall_quality,
                },
            )
            await event_emitter.emit(
                task_id,
                "observe:decision",
                {
                    "turn": current_turn,
                    "routeHint": route_hint,
                    "reason": reason,
                },
            )
        except Exception as exc:  # pragma: no cover - 防御性
            logger.warning("observe event emit failed: %s", exc)

    update: dict = {
        "observation_summary": observation_summary,
        "observation_quality": overall_quality,
        "observation_items": items,
        "consecutive_empty_observations": consecutive_empty,
        "last_error_category": last_error_category,
        "route_hint": route_hint,
        "phase": "observing",
    }
    if messages:
        update["messages"] = messages
    return update


# === LLM 完成声明质量评估 ===


async def _evaluate_completion(
    state: AgentState,
    event_emitter: Any,
    task_id: str,
    current_turn: int,
    previous_phase: str,
) -> dict:
    """评估 LLM 的完成声明质量

    这是 loop 完成的显式确认点，所有结束都必须通过此节点的判定。

    判定标准：
    1. 文本长度：过短可能未完成
    2. 包含实质性内容：不能只是“完成”两个字
    3. 是否包含结果摘要或关键信息

    Returns:
        状态更新字典，包含 route_hint 等
    """
    from src.infrastructure.agent.nodes.complete_check_node import rule_based_completion_check

    messages = state.get("messages", [])
    if not messages:
        return {"route_hint": "llm_call", "phase": "observing"}

    last_msg = messages[-1]
    text = ""
    if isinstance(last_msg, dict):
        text = last_msg.get("content", "") or ""
    elif hasattr(last_msg, "content"):
        text = last_msg.content or ""

    # 发射阶段变更事件
    if event_emitter is not None:
        try:
            if inspect.iscoroutinefunction(event_emitter.emit_phase_changed):
                await event_emitter.emit_phase_changed(
                    task_id, "evaluating_completion", previous_phase, current_turn,
                )
            else:
                event_emitter.emit_phase_changed(
                    task_id, "evaluating_completion", previous_phase, current_turn,
                )
        except Exception as exc:
            logger.warning("observe phase event failed: %s", exc)

    # 判定 1：是否真的声明了完成（使用规则快速判断）
    rule_result = rule_based_completion_check(text)
    if rule_result is not True:
        # 没有明确声明完成，回到 LLM
        return {
            "route_hint": "llm_call",
            "observation_quality": "incomplete",
            "phase": "observing",
        }

    # 判定 2：文本长度检查（至少 10 个字符）
    if len(text.strip()) < 10:
        logger.info(
            "Completion claim too short (%d chars), continuing",
            len(text.strip()),
        )
        return {
            "route_hint": "llm_call",
            "observation_summary": "Completion claim too brief",
            "observation_quality": "incomplete",
            "phase": "observing",
        }

    # 判定 3：检查是否包含实质性内容
    # 如果只有关键词但没有实际内容，认为未完成
    substantive_indicators = [
        "已创建", "已修改", "已删除", "已分析", "已实现",
        "created", "modified", "deleted", "analyzed", "implemented",
        "结果", "总结", "报告", "文件",
        "result", "summary", "report", "file",
    ]

    text_lower = text.lower()
    has_substance = any(indicator in text_lower for indicator in substantive_indicators)

    if not has_substance:
        logger.info("Completion claim lacks substantive content, continuing")
        return {
            "route_hint": "llm_call",
            "observation_summary": "Completion claim lacks details",
            "observation_quality": "incomplete",
            "phase": "observing",
        }

    # 判定 4：通过检查，确认完成
    logger.info("Completion claim validated by observe node, task complete")

    if event_emitter is not None:
        try:
            if inspect.iscoroutinefunction(event_emitter.emit):
                await event_emitter.emit(
                    task_id,
                    "completion:validated",
                    {
                        "turn": current_turn,
                        "quality": "complete",
                        "summary": text[:200],
                    },
                )
            else:
                event_emitter.emit(
                    task_id,
                    "completion:validated",
                    {
                        "turn": current_turn,
                        "quality": "complete",
                        "summary": text[:200],
                    },
                )
        except Exception as exc:
            logger.warning("emit completion event failed: %s", exc)

    return {
        "route_hint": "finalize",
        "observation_summary": "Task completion validated by observe node",
        "observation_quality": "complete",
        "final_result": text,
        "is_complete": True,
        "phase": "complete",
    }
