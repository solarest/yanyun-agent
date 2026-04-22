"""基础设施层 - 上下文压缩节点

LangGraph Node: context_compact_node
职责：当上下文接近 token 限制时压缩对话历史
"""

from langgraph.types import RunnableConfig

from src.domain.entities.agent_state import AgentState


async def context_compact_node(state: AgentState, config: RunnableConfig) -> dict:
    """上下文压缩节点

    策略：
    1. 保留系统提示和最近 N 条消息
    2. 压缩中间消息为摘要
    3. 发射压缩事件

    Args:
        state: 当前 Agent 状态
        config: LangGraph 配置

    Returns:
        状态更新字典
    """
    event_svc = config["configurable"]["event_service"]
    task_id = state["task_id"]
    messages = state["messages"]

    # 简单实现：只保留最近 10 条消息
    # 实际应使用 LLM 生成摘要
    max_messages = 10

    before_count = len(messages)
    if before_count > max_messages:
        # 保留系统消息和最近消息
        compressed = messages[:1] + messages[-(max_messages - 1) :]
        after_count = len(compressed)

        await event_svc.emit(
            task_id,
            "context-compacting",
            {
                "beforeTokens": before_count,
                "afterTokens": after_count,
            },
        )

        return {"messages": compressed}

    return {}
