"""共享压缩工具函数 — compact_messages() 从 ContextCompactNode._do_compact() 抽取

供 MicroCompactStrategy 和 EmergencyCompactStrategy 共享使用。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage, RemoveMessage, SystemMessage

from src.domain.services.token_utils import estimate_context_tokens
from src.infrastructure.agent.nodes.compaction.strategy import CompactionResult
from src.infrastructure.agent.nodes.compaction.summary_generator import SummaryGenerator

if TYPE_CHECKING:
    from langgraph.types import RunnableConfig
    from src.infrastructure.agent.nodes.base_node import NodeContext

logger = logging.getLogger(__name__)

MICRO_COMPACT_SUMMARY_MAX_MSGS = 90


async def compact_messages(
    messages: list,
    max_tokens: int,
    config: RunnableConfig,
    context: NodeContext,
    *,
    keep_recent: int,
    strategy: str,
    summary_generator: SummaryGenerator | None = None,
) -> CompactionResult:
    """通用消息压缩逻辑：摘要旧消息 + RemoveMessage

    保留：
    - 首条 SystemMessage（如果有）
    - 最近 keep_recent 条消息

    对中间的消息（最多 MICRO_COMPACT_SUMMARY_MAX_MSGS 条）做 LLM 摘要，
    其余更旧消息仅 RemoveMessage。

    Args:
        messages: 完整消息列表
        max_tokens: 上下文窗口 Token 上限
        config: LangGraph 配置
        context: 节点执行上下文
        keep_recent: 保留的最近消息数量
        strategy: 策略标识符
        summary_generator: 摘要生成器 (None 则使用默认实例)

    Returns:
        CompactionResult
    """
    if summary_generator is None:
        summary_generator = SummaryGenerator()

    before_count = len(messages)

    # 识别 SystemMessage
    system_idx = 0 if messages and isinstance(messages[0], SystemMessage) else -1
    preserve_start = system_idx + 1

    # 不足压缩阈值，跳过
    if before_count <= preserve_start + keep_recent + 1:
        logger.info(
            "[compaction:compact_messages] COMPACT_SKIP | task_id=%s | turn=%d | "
            "reason=too_few_messages | count=%d",
            context.task_id, context.current_turn, before_count,
        )
        return CompactionResult(
            strategy=strategy,
            messages=list(messages),
            token_estimate=estimate_context_tokens(messages),
            removed_count=0,
            baseline_invalidated=False,
        )

    # 待压缩消息: [preserve_start : -keep_recent]
    compact_end = -keep_recent
    to_compact = list(messages[preserve_start:compact_end])

    # 取最多 MICRO_COMPACT_SUMMARY_MAX_MSGS 条做摘要
    summary_candidates = to_compact[-MICRO_COMPACT_SUMMARY_MAX_MSGS:]
    extra_old = to_compact[: -MICRO_COMPACT_SUMMARY_MAX_MSGS] if len(to_compact) > MICRO_COMPACT_SUMMARY_MAX_MSGS else []

    # 构建汇总结果
    result_messages = []
    if system_idx >= 0:
        result_messages.append(messages[0])  # SystemMessage

    # RemoveMessage for extra old messages (beyond summary window)
    for msg in extra_old:
        msg_id = getattr(msg, "id", None)
        if msg_id:
            result_messages.append(RemoveMessage(id=msg_id))

    # Summary injection
    summary_text = await summary_generator.generate(
        summary_candidates, max_tokens, config, context,
    )

    if summary_text:
        # 用第一条被压缩消息的 id 放置摘要，保持时间线位置
        first_id = None
        for msg in to_compact:
            mid = getattr(msg, "id", None) if not isinstance(msg, RemoveMessage) else None
            if mid:
                first_id = mid
                break
        if first_id:
            result_messages.append(
                HumanMessage(
                    content=f"[Context Summary]\n{summary_text}",
                    id=first_id,
                )
            )
        else:
            result_messages.append(
                HumanMessage(content=f"[Context Summary]\n{summary_text}")
            )

        # RemoveMessage for summarized messages
        for msg in to_compact:
            msg_id = getattr(msg, "id", None)
            if msg_id:
                result_messages.append(RemoveMessage(id=msg_id))
    else:
        # LLM 不可用/失败：纯 trim（只 RemoveMessage）
        for msg in to_compact:
            msg_id = getattr(msg, "id", None)
            if msg_id:
                result_messages.append(RemoveMessage(id=msg_id))

    # 保留最近的消息
    result_messages.extend(messages[compact_end:])

    after_count = len([m for m in result_messages if not isinstance(m, RemoveMessage)])
    removed_count = before_count - after_count + (1 if summary_text else 0)
    after_tokens = estimate_context_tokens(result_messages)

    logger.info(
        "[compaction:compact_messages] %s_COMPLETE | task_id=%s | "
        "before_count=%d | after_count=%d | removed=%d | "
        "before_tokens_est=%d | summary_length=%d",
        strategy.upper(), context.task_id,
        before_count, after_count, removed_count,
        after_tokens, len(summary_text or ""),
    )

    return CompactionResult(
        strategy=strategy,
        messages=result_messages,
        token_estimate=after_tokens,
        removed_count=removed_count,
        baseline_invalidated=True,
    )
