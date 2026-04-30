"""基础设施层 - 上下文压缩节点

LangGraph Node: context_compact_node
职责：当上下文接近 token 限制时压缩对话历史

使用 LangGraph 原生的 RemoveMessage 操作来正确删除中间消息，
与 add_messages reducer 兼容。
"""

from langchain_core.messages import RemoveMessage
from langgraph.types import RunnableConfig

from src.domain.entities.agent_state import AgentState


async def context_compact_node(state: AgentState, config: RunnableConfig) -> dict:
    """上下文压缩节点

    策略：
    1. 保留第一条消息（SystemMessage）和最近 N 条消息
    2. 通过 RemoveMessage 删除中间消息（与 add_messages reducer 兼容）
    3. 发射压缩事件

    Args:
        state: 当前 Agent 状态
        config: LangGraph 配置

    Returns:
        状态更新字典
    """
    event_emitter = (
        config["configurable"].get("event_emitter")
        or config["configurable"]["event_service"]
    )
    task_id = state["task_id"]
    messages = state["messages"]
    current_turn = state.get("current_turn", 0)

    await event_emitter.emit_phase_changed(
        task_id,
        "context_compacting",
        state.get("phase", "thinking"),
        current_turn,
    )

    keep_recent = 10
    before_count = len(messages)

    if before_count <= keep_recent + 1:
        # 消息不多，无需压缩
        return {"phase": "context_compacting"}

    # 需要删除的消息：跳过第 1 条（SystemMessage）和最后 keep_recent 条
    to_remove = messages[1 : -(keep_recent)]
    remove_ops = []
    for msg in to_remove:
        msg_id = getattr(msg, "id", None)
        if msg_id:
            remove_ops.append(RemoveMessage(id=msg_id))

    after_count = before_count - len(remove_ops)

    await event_emitter.emit(
        task_id,
        "context:compacting",
        {
            "beforeCount": before_count,
            "afterCount": after_count,
            "removedCount": len(remove_ops),
        },
    )

    if remove_ops:
        return {"messages": remove_ops, "phase": "context_compacting"}

    return {"phase": "context_compacting"}
