"""SoftPruneStrategy — 软裁剪 (priority=1)

裁剪超长 ToolMessage 内容，目标降到 25% 水线。
移植自 ContextCompactNode._soft_prune()。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from langchain_core.messages import ToolMessage
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

SOFT_PRUNE_WATERMARK = 0.4
SOFT_PRUNE_TARGET = 0.25
SOFT_PRUNE_MIN_CONTENT_LENGTH = 20000
SOFT_PRUNE_HEAD_TAIL = 4000


class SoftPruneStrategy(CompactionStrategy):
    """软裁剪：截断超长工具调用结果"""

    @property
    def name(self) -> str:
        return "soft_prune"

    @property
    def priority(self) -> int:
        return 1

    def should_apply(
        self,
        state: AgentState,
        messages: list,
        current_tokens: int,
        max_tokens: int,
    ) -> bool:
        return current_tokens > int(max_tokens * SOFT_PRUNE_WATERMARK)

    async def apply(
        self,
        state: AgentState,
        messages: list,
        current_tokens: int,
        max_tokens: int,
        config: RunnableConfig,
        context: NodeContext,
    ) -> CompactionResult:
        target_tokens = int(max_tokens * SOFT_PRUNE_TARGET)
        pruned_count = 0
        modified_messages = []

        for index, msg in enumerate(messages):
            is_tool_msg = isinstance(msg, ToolMessage) or (
                isinstance(msg, dict) and msg.get("role") == "tool"
            )

            if not is_tool_msg:
                modified_messages.append(msg)
                continue

            content = (
                msg.content if hasattr(msg, "content") else msg.get("content", "")
            ) or ""

            if len(content) <= SOFT_PRUNE_MIN_CONTENT_LENGTH:
                modified_messages.append(msg)
                continue

            # 裁剪: head + notice + tail
            head = content[:SOFT_PRUNE_HEAD_TAIL]
            tail = content[-SOFT_PRUNE_HEAD_TAIL:]
            pruned_content = (
                f"{head}\n\n"
                f"[... tool result soft-pruned; middle omitted ...]\n\n"
                f"{tail}"
            )

            if isinstance(msg, dict):
                new_msg = {**msg, "content": pruned_content}
            else:
                kwargs: dict[str, Any] = {"content": pruned_content}
                msg_id = getattr(msg, "id", None)
                if msg_id:
                    kwargs["id"] = msg_id
                tool_call_id = getattr(msg, "tool_call_id", None)
                if tool_call_id:
                    kwargs["tool_call_id"] = tool_call_id
                name = getattr(msg, "name", None)
                if name:
                    kwargs["name"] = name
                new_msg = ToolMessage(**kwargs)

            modified_messages.append(new_msg)
            pruned_count += 1

            # 检查是否已达目标
            new_estimate = estimate_context_tokens(modified_messages)
            if new_estimate <= target_tokens:
                modified_messages.extend(messages[index + 1:])
                break

        after_tokens = estimate_context_tokens(modified_messages)

        logger.info(
            "[compaction:soft_prune] SOFT_PRUNE_COMPLETE | task_id=%s | turn=%d | "
            "before_tokens=%d | after_tokens=%d | pruned=%d | target=%d",
            context.task_id, context.current_turn,
            current_tokens, after_tokens, pruned_count, target_tokens,
        )

        return CompactionResult(
            strategy="soft_prune",
            messages=modified_messages,
            token_estimate=after_tokens,
            removed_count=0,
            baseline_invalidated=pruned_count > 0,
            pruned_count=pruned_count,
        )
