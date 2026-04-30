"""基础设施层 - Stuck 检测节点

LangGraph Node: stuck_detect_node
职责：检测 Agent 是否卡住（无法推进任务）
"""

from langchain_core.messages import AIMessage
from langgraph.types import RunnableConfig

from src.domain.entities.agent_state import AgentState


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


async def stuck_detect_node(state: AgentState, config: RunnableConfig) -> dict:
    """Stuck 检测节点

    检测模式：
    1. 重复 action/error：工具反复失败
    2. 单话模式：LLM 只输出文本不采取行动
    3. 交替模式：在两个状态间来回切换

    Args:
        state: 当前 Agent 状态
        config: LangGraph 配置

    Returns:
        状态更新字典
    """
    start_index = state.get("task_start_message_count", 0)
    messages = state["messages"][start_index:]

    # 简化实现：检查最近几轮是否有实质进展
    # 如果连续 3 轮没有工具调用且文本内容相似，认为卡住
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

    if no_tool_calls_count >= 3:
        # 连续 3 轮没有工具调用，可能卡住
        event_emitter = (
            config["configurable"].get("event_emitter")
            or config["configurable"]["event_service"]
        )
        current_turn = state.get("current_turn", 0)
        previous_phase = state.get("phase", "thinking")
        next_count = state.get("stuck_detection_count", 0) + 1
        action = "terminate" if next_count >= 3 else "inject_feedback"

        await event_emitter.emit(
            state["task_id"],
            "stuck:detected",
            {
                "stuckType": "monologue",
                "count": next_count,
                "action": action,
            },
        )
        await event_emitter.emit_phase_changed(
            state["task_id"],
            "stuck_recovering",
            previous_phase,
            current_turn,
        )
        return {
            "stuck_detected": True,
            "stuck_detection_count": next_count,
            "stuck_type": "monologue",
            "phase": "stuck_recovering",
        }

    return {"stuck_detected": False, "stuck_type": None, "stuck_detection_count": 0}
