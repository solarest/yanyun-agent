"""基础设施层 - 上下文压缩节点

LangGraph Node: context_compact_node
职责:当上下文接近 token 限制时压缩对话历史

支持两种压缩策略:
- trim(默认):保留首条 SystemMessage + 尾部 N 条,RemoveMessage 中间部分
- summarize:调用 LLM 对待移除消息生成摘要,注入摘要 HumanMessage + RemoveMessage 原消息

使用 LangGraph 原生的 RemoveMessage 操作来正确删除中间消息,
与 add_messages reducer 兼容。
"""

import logging

from langchain_core.messages import HumanMessage, RemoveMessage, SystemMessage
from langgraph.types import RunnableConfig

from src.domain.aggregates.agent.agent_state import AgentState
from src.infrastructure.agent.nodes.base_node import BaseNode, NodeContext

logger = logging.getLogger(__name__)

# LLM 摘要压缩的 system prompt
_SUMMARIZE_SYSTEM_PROMPT = (
    "You are a conversation summarizer. Summarize the following conversation messages "
    "into a concise summary that preserves:\n"
    "1. Key decisions and actions taken\n"
    "2. Important tool call results (success/failure)\n"
    "3. Error messages and what was tried\n"
    "4. Current task progress\n\n"
    "Be concise but preserve critical context. Output only the summary."
)


class ContextCompactNode(BaseNode):
    """上下文压缩节点"""

    @property
    def node_name(self) -> str:
        return "context_compact"

    @property
    def default_phase(self) -> str:
        return "context_compacting"

    async def execute(self, state: AgentState, config: RunnableConfig, context: NodeContext) -> dict:
        """执行上下文压缩

        策略由 state['compression_strategy'] 决定:
        - "trim"(默认):裁剪中间消息
        - "summarize":LLM 摘要 + 裁剪

        Args:
            state: 当前 Agent 状态
            config: LangGraph 配置
            context: 节点执行上下文

        Returns:
            状态更新字典
        """
        current_turn = context.current_turn
        messages = state["messages"]
        strategy = state.get("compression_strategy") or "trim"

        keep_recent = 10
        before_count = len(messages)

        if before_count <= keep_recent + 1:
            # 消息不多,无需压缩
            logger.info(
                "[NODE:context_compact] SKIP_COMPACT | task_id=%s | turn=%d | "
                "reason=messages_count_low | count=%d",
                context.task_id, current_turn, before_count
            )
            return {"phase": "context_compacting", "compression_strategy": None}

        # 需要删除的消息:跳过第 1 条(SystemMessage)和最后 keep_recent 条
        to_remove = messages[1: -(keep_recent)]

        logger.info(
            "[NODE:context_compact] COMPACT_PLANNED | task_id=%s | turn=%d | "
            "before_count=%d | to_remove_count=%d | strategy=%s",
            context.task_id, current_turn, before_count, len(
                to_remove), strategy
        )

        if strategy == "summarize":
            return await _summarize_and_compact(
                state, config, context.event_emitter, context.task_id,
                messages, to_remove, before_count, keep_recent,
            )

        # 默认 trim 策略
        return await _trim_compact(
            context.event_emitter, context.task_id, to_remove, before_count,
        )


# 保持向后兼容的实例导出
context_compact_node = ContextCompactNode()


async def _trim_compact(
    event_emitter,
    task_id: str,
    to_remove: list,
    before_count: int,
) -> dict:
    """Trim 策略：直接 RemoveMessage 中间消息"""
    remove_ops = []
    for msg in to_remove:
        msg_id = getattr(msg, "id", None)
        if msg_id:
            remove_ops.append(RemoveMessage(id=msg_id))

    after_count = before_count - len(remove_ops)

    logger.info(
        "[NODE:context_compact] TRIM_COMPLETE | task_id=%s | "
        "before_count=%d | after_count=%d | removed_count=%d",
        task_id, before_count, after_count, len(remove_ops)
    )

    await event_emitter.emit(
        task_id,
        "context:compacting",
        {
            "strategy": "trim",
            "beforeCount": before_count,
            "afterCount": after_count,
            "removedCount": len(remove_ops),
        },
    )

    if remove_ops:
        return {
            "messages": remove_ops,
            "phase": "context_compacting",
            "compression_strategy": None,
        }
    return {"phase": "context_compacting", "compression_strategy": None}


async def _summarize_and_compact(
    state: AgentState,
    config: RunnableConfig,
    event_emitter,
    task_id: str,
    messages: list,
    to_remove: list,
    before_count: int,
    keep_recent: int,
) -> dict:
    """Summarize 策略：LLM 摘要 + RemoveMessage"""
    llm = config.get("configurable", {}).get("llm")

    if not llm:
        logger.warning(
            "LLM not available for summarization, falling back to trim")
        return await _trim_compact(event_emitter, task_id, to_remove, before_count)

    # 构建摘要输入：提取待移除消息的文本内容
    summary_parts = []
    for msg in to_remove:
        role = "unknown"
        content = ""
        if hasattr(msg, "type"):
            role = msg.type
        elif isinstance(msg, dict):
            role = msg.get("role", "unknown")

        if hasattr(msg, "content"):
            content = msg.content or ""
        elif isinstance(msg, dict):
            content = msg.get("content", "") or ""

        if content:
            # 截断过长的单条消息
            if len(content) > 500:
                content = content[:500] + "..."
            summary_parts.append(f"[{role}] {content}")

    if not summary_parts:
        return await _trim_compact(event_emitter, task_id, to_remove, before_count)

    # 调用 LLM 生成摘要
    try:
        summary_input = "\n\n".join(summary_parts)
        # 限制总输入长度
        if len(summary_input) > 4000:
            summary_input = summary_input[:4000] + "\n\n...(truncated)"

        # LLM 摘要调用前日志
        logger.info(
            "[NODE:context_compact] LLM_SUMMARIZE_INPUT | task_id=%s | turn=%d | "
            "input_length=%d | messages_to_summarize=%d",
            task_id, state.get("current_turn", 0), len(
                summary_input), len(to_remove)
        )

        response = await llm.ainvoke([
            SystemMessage(content=_SUMMARIZE_SYSTEM_PROMPT),
            HumanMessage(
                content=f"Conversation to summarize:\n\n{summary_input}"),
        ])

        summary_text = response.content if hasattr(
            response, "content") else str(response)

        # LLM 摘要成功日志
        logger.info(
            "[NODE:context_compact] LLM_SUMMARIZE_OUTPUT | task_id=%s | turn=%d | "
            "summary_length=%d",
            task_id, state.get("current_turn", 0), len(summary_text)
        )
    except Exception as e:
        # LLM 摘要失败日志
        logger.warning(
            "[NODE:context_compact] LLM_SUMMARIZE_ERROR | task_id=%s | turn=%d | "
            "error=%s | fallback=trim",
            task_id, state.get("current_turn", 0), str(e)
        )
        return await _trim_compact(event_emitter, task_id, to_remove, before_count)

    # 构建结果：RemoveMessage + 摘要 HumanMessage
    result_messages = []

    # 先 RemoveMessage
    for msg in to_remove:
        msg_id = getattr(msg, "id", None)
        if msg_id:
            result_messages.append(RemoveMessage(id=msg_id))

    # 再注入摘要消息
    result_messages.append(
        HumanMessage(content=f"[Context Summary]\n{summary_text}")
    )

    after_count = before_count - len(to_remove) + 1  # +1 for summary message

    await event_emitter.emit(
        task_id,
        "context:compacting",
        {
            "strategy": "summarize",
            "beforeCount": before_count,
            "afterCount": after_count,
            "removedCount": len(to_remove),
            "summaryLength": len(summary_text),
        },
    )

    # Node 完成日志
    logger.info(
        "[NODE:context_compact] SUMMARIZE_COMPLETE | task_id=%s | "
        "before_count=%d | after_count=%d | summary_length=%d",
        task_id, before_count, after_count, len(summary_text),
    )

    return {
        "messages": result_messages,
        "phase": "context_compacting",
        "compression_strategy": None,
    }
