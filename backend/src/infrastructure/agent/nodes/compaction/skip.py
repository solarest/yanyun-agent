"""SkipStrategy — 兜底策略 (priority=0)

should_apply() 永远返回 True，apply() 不修改 messages。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from langgraph.types import RunnableConfig

from src.domain.services.token_utils import estimate_context_tokens
from src.infrastructure.agent.nodes.compaction.strategy import (
    CompactionResult,
    CompactionStrategy,
)

if TYPE_CHECKING:
    from src.domain.aggregates.agent.agent_state import AgentState
    from src.infrastructure.agent.nodes.base_node import NodeContext

logger = logging.getLogger(__name__)


class SkipStrategy(CompactionStrategy):
    """跳过压缩：兜底策略，不修改任何消息"""

    @property
    def name(self) -> str:
        return "skip"

    @property
    def priority(self) -> int:
        return 0

    def should_apply(
        self,
        state: AgentState,
        messages: list,
        current_tokens: int,
        max_tokens: int,
    ) -> bool:
        return True

    async def apply(
        self,
        state: AgentState,
        messages: list,
        current_tokens: int,
        max_tokens: int,
        config: RunnableConfig,
        context: NodeContext,
    ) -> CompactionResult:
        logger.info(
            "[compaction:skip] WATERMARK | task_id=%s | turn=%d | "
            "tokens=%d/%d | strategy=skip | reason=below_watermark",
            context.task_id, context.current_turn, current_tokens, max_tokens,
        )
        return CompactionResult(
            strategy="skip",
            messages=list(messages),
            token_estimate=current_tokens,
            removed_count=0,
            baseline_invalidated=False,
        )
