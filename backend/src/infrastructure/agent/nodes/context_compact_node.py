"""基础设施层 - 上下文压缩节点 (策略模式重构)

LangGraph Node: context_compact_node
职责: 每轮 LLM 调用前检查 Token 水位，按优先级选择并执行压缩策略。

策略链 (按 priority 降序):
1. emergency-compact (priority=3): 上下文超限后紧急压缩 (保留最近 3 条)
2. micro-compact (priority=2): token > 60% 水线 (保留最近 10 条，摘要旧消息)
3. soft-prune (priority=1): token > 40% 水线 (裁剪超长工具结果)
4. skip (priority=0): 低于 40% 水线 (不处理，兜底)

使用 LangGraph 原生的 RemoveMessage 操作来正确删除中间消息，
与 add_messages reducer 兼容。
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import RemoveMessage
from langgraph.types import RunnableConfig

from src.domain.aggregates.agent.agent_state import AgentState
from src.domain.entities.event_types import AgentEventType
from src.domain.services.token_utils import estimate_context_tokens
from src.infrastructure.agent.nodes.base_node import BaseNode, NodeContext
from src.infrastructure.agent.nodes.compaction import (
    CompactionStrategy,
    _default_strategies,
)

logger = logging.getLogger(__name__)


class ContextCompactNode(BaseNode):
    """上下文压缩节点 — 薄编排层，委托策略链执行

    每轮 LLM 调用前，按 priority 降序遍历策略链，
    执行第一个 should_apply() 返回 True 的策略。
    """

    def __init__(self, strategies: list[CompactionStrategy] | None = None) -> None:
        if strategies is None:
            strategies = _default_strategies()
        # 确保按 priority 降序排列
        self._strategies = sorted(strategies, key=lambda s: s.priority, reverse=True)

    @property
    def node_name(self) -> str:
        return "context_compact"

    @property
    def default_phase(self) -> str:
        return "context_compacting"

    async def execute(
        self, state: AgentState, config: RunnableConfig, context: NodeContext
    ) -> dict:
        max_tokens = state.get("max_context_tokens", 128_000)
        messages = list(state["messages"])
        baseline = state.get("context_token_baseline")
        baseline_count = state.get("context_token_baseline_message_count", 0)
        current_tokens = estimate_context_tokens(messages, baseline, baseline_count)

        # 按 priority 降序遍历策略链，执行第一个匹配的策略
        chosen: CompactionStrategy | None = None
        for strategy in self._strategies:
            if strategy.should_apply(state, messages, current_tokens, max_tokens):
                chosen = strategy
                break

        if chosen is None:
            # 防御性：不应该出现（SkipStrategy 永远返回 True）
            logger.warning(
                "[NODE:context_compact] NO_STRATEGY_MATCHED | task_id=%s",
                context.task_id,
            )
            return await self._build_result(state, messages, current_tokens, max_tokens, context, "skip")

        result = await chosen.apply(state, messages, current_tokens, max_tokens, config, context)
        return await self._build_result(
            state, result.messages, result.token_estimate, max_tokens, context,
            result.strategy, result,
        )

    async def _build_result(
        self,
        state: AgentState,
        messages: list,
        tokens: int,
        max_tokens: int,
        context: NodeContext,
        strategy: str,
        compaction_result: Any = None,
    ) -> dict:
        """构建 state update 字典并 emit event"""
        before_messages = list(state["messages"])
        before_tokens = estimate_context_tokens(before_messages)

        removed_count = getattr(compaction_result, "removed_count", 0) if compaction_result else 0

        event_data: dict = {
            "strategy": strategy,
            "beforeTokens": before_tokens,
            "afterTokens": tokens,
            "maxContextTokens": max_tokens,
            "beforeCount": len(before_messages),
            "afterCount": len([m for m in messages if not isinstance(m, RemoveMessage)]),
            "removedCount": removed_count,
        }

        if strategy == "soft_prune" and compaction_result is not None:
            event_data["prunedToolResults"] = getattr(compaction_result, "pruned_count", 0)

        if strategy == "skip":
            event_data["reason"] = "below_watermark"
        elif strategy == "soft_prune":
            event_data["reason"] = "watermark_40"
        elif strategy == "micro_compact":
            event_data["reason"] = "watermark_60"
        elif strategy == "emergency_compact":
            event_data["reason"] = "context_overflow"

        # Emit event
        await context.event_emitter.emit(
            context.task_id,
            AgentEventType.CONTEXT_COMPACTING,
            event_data,
        )

        # 使用 CompactionResult.to_state_update() 或手动构建
        if compaction_result is not None and hasattr(compaction_result, "to_state_update"):
            update = compaction_result.to_state_update()
            update["phase"] = "context_compacting"
        else:
            update = {
                "phase": "context_compacting",
                "context_token_estimate": tokens,
                "last_context_strategy": strategy,
            }

        # skip 策略不修改 messages
        if strategy == "skip":
            update.pop("messages", None)

        return update


# 保持向后兼容的实例导出
context_compact_node = ContextCompactNode()
