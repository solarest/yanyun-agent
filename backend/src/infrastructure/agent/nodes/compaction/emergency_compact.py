"""EmergencyCompactStrategy — 紧急压缩 (priority=3)

LLM 上下文超限后触发，保留 SystemMessage + 最近 3 条，对旧消息做 LLM 摘要。
移植自 ContextCompactNode._emergency_compact()。
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

EMERGENCY_COMPACT_KEEP_RECENT = 3


class EmergencyCompactStrategy(CompactionStrategy):
    """紧急压缩：上下文超限后触发，保留最近 3 条 + 摘要旧消息"""

    @property
    def name(self) -> str:
        return "emergency_compact"

    @property
    def priority(self) -> int:
        return 3

    def should_apply(
        self,
        state: AgentState,
        messages: list,
        current_tokens: int,
        max_tokens: int,
    ) -> bool:
        return state.get("emergency_compact_requested", False)

    async def apply(
        self,
        state: AgentState,
        messages: list,
        current_tokens: int,
        max_tokens: int,
        config: RunnableConfig,
        context: NodeContext,
    ) -> CompactionResult:
        attempts = state.get("context_compaction_attempts", 0) + 1

        logger.warning(
            "[compaction:emergency] EMERGENCY_COMPACT | task_id=%s | turn=%d | "
            "attempt=%d | before_tokens=%d",
            context.task_id, context.current_turn, attempts, current_tokens,
        )

        result = await compact_messages(
            messages,
            max_tokens,
            config,
            context,
            keep_recent=EMERGENCY_COMPACT_KEEP_RECENT,
            strategy="emergency_compact",
        )
        result.compaction_attempts = attempts
        result.clear_emergency = True
        return result
