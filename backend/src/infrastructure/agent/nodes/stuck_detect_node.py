"""基础设施层 - Stuck 检测节点

LangGraph Node: stuck_detect_node
职责：检测 Agent 是否卡住（无法推进任务）
"""

from langgraph.types import RunnableConfig

from src.domain.entities.agent_state import AgentState


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
    messages = state["messages"]

    # 简化实现：检查最近几轮是否有实质进展
    # 如果连续 3 轮没有工具调用且文本内容相似，认为卡住
    recent_assistant_msgs = []
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get("role") == "assistant":
            recent_assistant_msgs.append(msg)
            if len(recent_assistant_msgs) >= 3:
                break

    # 检查是否连续没有工具调用
    no_tool_calls_count = 0
    for msg in recent_assistant_msgs:
        if not msg.get("tool_calls"):
            no_tool_calls_count += 1

    if no_tool_calls_count >= 3:
        # 连续 3 轮没有工具调用，可能卡住
        return {
            "stuck_detected": True,
            "stuck_detection_count": state.get("stuck_detection_count", 0) + 1,
            "stuck_type": "monologue",
        }

    return {"stuck_detected": False, "stuck_type": None}
