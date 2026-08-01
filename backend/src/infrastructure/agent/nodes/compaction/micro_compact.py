"""MicroCompactStrategy — 微压缩 (priority=2)

保留 SystemMessage + 最近 10 条，对旧消息做 LLM 摘要。
移植自 ContextCompactNode._micro_compact()。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from langgraph.types import RunnableConfig

from src.infrastructure.agent.nodes.compaction.compact_utils import compact_messages
from src.infrastructure.agent.nodes.compaction.strategy import (
    CompactionResult,
    CompactionStrategy,
)

if TYPE_CHECKING:
    from src.domain.aggregates.agent.agent_state import AgentState
    from src.infrastructure.agent.nodes.base_node import NodeContext

logger = logging.getLogger(__name__)

MICRO_COMPACT_WATERMARK = 0.6
MICRO_COMPACT_KEEP_RECENT = 10


class MicroCompactStrategy(CompactionStrategy):
    """微压缩：Token > 60% 水线时触发，保留最近 10 条 + 摘要旧消息"""

    @property
    def name(self) -> str:
        return "micro_compact"

    @property
    def priority(self) -> int:
        return 2

    def should_apply(
        self,
        state: AgentState,
        messages: list,
        current_tokens: int,
        max_tokens: int,
    ) -> bool:
        return current_tokens > int(max_tokens * MICRO_COMPACT_WATERMARK)

    async def apply(
        self,
        state: AgentState,
        messages: list,
        current_tokens: int,
        max_tokens: int,
        config: RunnableConfig,
        context: NodeContext,
    ) -> CompactionResult:
        return await compact_messages(
            messages,
            max_tokens,
            config,
            context,
            keep_recent=MICRO_COMPACT_KEEP_RECENT,
            strategy="micro_compact",
        )
