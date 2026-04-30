"""基础设施层 - Loop 检测节点

LangGraph Node: loop_detect_node
职责：检测 Agent 是否进入循环模式
"""

import hashlib
import json
from collections import Counter

from langchain_core.messages import AIMessage
from langgraph.types import RunnableConfig

from src.domain.entities.agent_state import AgentState


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
    """稳定的参数哈希，支持嵌套 JSON 结构。"""
    canonical = json.dumps(args or {}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


async def loop_detect_node(state: AgentState, config: RunnableConfig) -> dict:
    """Loop 检测节点

    检测策略：
    1. 精确匹配：最近 N 轮是否调用相同工具 + 相同参数
    2. 内容相似度：LLM 响应文本相似度

    Args:
        state: 当前 Agent 状态
        config: LangGraph 配置

    Returns:
        状态更新字典 (包含 loop_detected 标志)
    """
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
        # 检查最近 N 轮工具调用是否相同
        signatures = []
        for tc_list in recent_tool_calls[:threshold]:
            if not tc_list:
                break
            # 工具名 + 参数 hash
            sig = tuple(
                (
                    tc.get("name"),
                    _hash_tool_args(tc.get("args") or tc.get("arguments") or {}),
                )
                for tc in tc_list
            )
            signatures.append(sig)

        if len(signatures) == threshold and len(set(signatures)) == 1:
            loop_detected = True
            loop_type = "exact_tool_repeat"

    # 内容相似度检测 (简化版：基于词袋重叠)
    if not loop_detected:
        assistant_texts = []
        for msg in reversed(messages):
            text = _assistant_text(msg)
            if text:
                assistant_texts.append(text)
                if len(assistant_texts) >= 4:
                    break

        if len(assistant_texts) >= 2:
            similarities = []
            for i in range(len(assistant_texts) - 1):
                words1 = Counter(assistant_texts[i].split())
                words2 = Counter(assistant_texts[i + 1].split())
                intersection = sum((words1 & words2).values())
                union = sum((words1 | words2).values())
                sim = intersection / union if union > 0 else 0
                similarities.append(sim)

            if similarities and all(s > 0.85 for s in similarities):
                loop_detected = True
                loop_type = "content_repeat"

    if loop_detected:
        event_emitter = (
            config["configurable"].get("event_emitter")
            or config["configurable"]["event_service"]
        )
        current_turn = state.get("current_turn", 0)
        previous_phase = state.get("phase", "thinking")
        next_count = state.get("loop_detection_count", 0) + 1
        action = "inject_feedback"
        if next_count == 2:
            action = "compact_context"
        elif next_count >= 3:
            action = "terminate"

        await event_emitter.emit(
            state["task_id"],
            "loop:detected",
            {
                "loopType": loop_type,
                "count": next_count,
                "action": action,
            },
        )
        await event_emitter.emit_phase_changed(
            state["task_id"],
            "loop_correcting",
            previous_phase,
            current_turn,
        )
        return {
            "loop_detected": True,
            "loop_detection_count": next_count,
            "loop_type": loop_type,
            "phase": "loop_correcting",
        }

    return {"loop_detected": False, "loop_type": None, "loop_detection_count": 0}
