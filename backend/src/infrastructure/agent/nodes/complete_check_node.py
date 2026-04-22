"""基础设施层 - 完成检查节点

LangGraph Node: complete_check_node
职责：检查 LLM 是否声明任务完成，并验证完成条件
"""

from langgraph.types import RunnableConfig

from src.domain.entities.agent_state import AgentState


# 完成声明的关键词
COMPLETION_PHRASES = [
    "task complete",
    "i have completed",
    "i've completed",
    "the task is done",
    "everything is done",
    "all done",
]


def is_claiming_complete(text: str) -> bool:
    """检查 LLM 是否声明任务完成"""
    text_lower = text.lower()
    return any(phrase in text_lower for phrase in COMPLETION_PHRASES)


async def complete_check_node(state: AgentState, config: RunnableConfig) -> dict:
    """完成检查节点

    1. 检查 LLM 是否声明完成
    2. 如果声明完成，设置 final_result
    3. 如果未完成，返回需要继续执行

    Args:
        state: 当前 Agent 状态
        config: LangGraph 配置

    Returns:
        状态更新字典
    """
    messages = state["messages"]
    if not messages:
        return {"is_complete": False}

    last_msg = messages[-1]
    text = ""
    if isinstance(last_msg, dict):
        text = last_msg.get("content", "")
    elif hasattr(last_msg, "content"):
        text = last_msg.content

    if is_claiming_complete(text):
        return {
            "is_complete": True,
            "final_result": text,
            "phase": "completed",
        }

    return {"is_complete": False}
