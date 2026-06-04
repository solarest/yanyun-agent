"""基础设施层 - 上下文压缩节点

LangGraph Node: context_compact_node
职责: 每轮 LLM 调用前检查 Token 水位，执行对应压缩策略。

4 级策略（按优先级）:
1. emergency-compact: 上下文超限后紧急压缩（保留最近 3 条）
2. micro-compact: token > 60% 水线（保留最近 10 条，摘要旧消息）
3. soft-prune: token > 40% 水线（裁剪超长工具结果）
4. skip: 低于 40% 水线（不处理）

使用 LangGraph 原生的 RemoveMessage 操作来正确删除中间消息，
与 add_messages reducer 兼容。
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.types import RunnableConfig

from src.domain.aggregates.agent.agent_state import AgentState
from src.domain.entities.event_types import AgentEventType
from src.domain.services.token_utils import (
    count_tokens,
    estimate_context_tokens,
    render_message,
)
from src.infrastructure.agent.nodes.base_node import BaseNode, NodeContext

logger = logging.getLogger(__name__)

# ── 任务聚焦摘要 Prompt（替代旧的通用摘要 prompt）───────────────

_COMPACTION_SUMMARY_PROMPT = (
    "You are compacting an agent execution context.\n\n"
    "Summarize the older messages so the agent can continue the same task "
    "without losing operational state.\n\n"
    "Focus on:\n"
    "1. What has already been completed.\n"
    "2. What is currently in progress.\n"
    "3. Files, paths, commands, tools, and external resources that were "
    "read, created, or modified.\n"
    "4. Important tool results, including success/failure and exact error "
    "messages when relevant.\n"
    "5. User constraints, preferences, and explicit instructions that still apply.\n"
    "6. What the agent should do next.\n\n"
    "Rules:\n"
    "- Preserve concrete filenames, IDs, function names, command outputs, "
    "and decisions.\n"
    "- Do not invent work that was not done.\n"
    "- If something is uncertain, label it as uncertain.\n"
    "- Keep the summary concise but operationally complete.\n"
    "- Output only the summary."
)

# ── 水线常量 ─────────────────────────────────────────────────

SOFT_PRUNE_WATERMARK = 0.4
MICRO_COMPACT_WATERMARK = 0.6
SOFT_PRUNE_TARGET = 0.25
SOFT_PRUNE_MIN_CONTENT_LENGTH = 20000
SOFT_PRUNE_HEAD_TAIL = 4000
MICRO_COMPACT_KEEP_RECENT = 10
EMERGENCY_COMPACT_KEEP_RECENT = 3
MICRO_COMPACT_SUMMARY_MAX_MSGS = 90
SUMMARY_MAX_INPUT_CHARS = 32000
SUMMARY_MAX_TOKEN_FRACTION = 0.05


class ContextCompactNode(BaseNode):
    """上下文压缩节点 — 每轮 LLM 前置守门"""

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

        is_emergency = (
            state.get("emergency_compact_requested", False)
            or state.get("compression_strategy") == "emergency_compact"
        )

        # Priority 1: Emergency compact
        if is_emergency:
            return await self._emergency_compact(
                state, messages, current_tokens, max_tokens, config, context
            )

        # Priority 2: Micro-compact (> 60%)
        if current_tokens > int(max_tokens * MICRO_COMPACT_WATERMARK):
            return await self._micro_compact(
                state, messages, current_tokens, max_tokens, config, context
            )

        # Priority 3: Soft-prune (> 40%)
        if current_tokens > int(max_tokens * SOFT_PRUNE_WATERMARK):
            return await self._soft_prune(
                state, messages, current_tokens, max_tokens, config, context
            )

        # Skip
        return await self._skip_compact(messages, current_tokens, max_tokens, context)

    # ── Skip ──────────────────────────────────────────────────

    async def _skip_compact(
        self,
        messages: list,
        current_tokens: int,
        max_tokens: int,
        context: NodeContext,
    ) -> dict:
        logger.info(
            "[NODE:context_compact] WATERMARK | task_id=%s | turn=%d | "
            "tokens=%d/%d | strategy=skip | reason=below_watermark",
            context.task_id, context.current_turn, current_tokens, max_tokens,
        )
        await context.event_emitter.emit(
            context.task_id,
            AgentEventType.CONTEXT_COMPACTING,
            {
                "strategy": "skip",
                "beforeTokens": current_tokens,
                "afterTokens": current_tokens,
                "maxContextTokens": max_tokens,
                "beforeCount": len(messages),
                "afterCount": len(messages),
                "removedCount": 0,
                "reason": "below_watermark",
            },
        )
        return {
            "phase": "context_compacting",
            "context_token_estimate": current_tokens,
            "last_context_strategy": "skip",
        }

    # ── Soft-prune ────────────────────────────────────────────

    async def _soft_prune(
        self,
        state: AgentState,
        messages: list,
        current_tokens: int,
        max_tokens: int,
        config: RunnableConfig,
        context: NodeContext,
    ) -> dict:
        """裁剪超长 ToolMessage 内容，目标降到 25% 水线"""
        target_tokens = int(max_tokens * SOFT_PRUNE_TARGET)
        pruned_count = 0
        modified_messages = []

        for msg in messages:
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
                break

        after_tokens = estimate_context_tokens(modified_messages)

        logger.info(
            "[NODE:context_compact] SOFT_PRUNE_COMPLETE | task_id=%s | turn=%d | "
            "before_tokens=%d | after_tokens=%d | pruned=%d | target=%d",
            context.task_id, context.current_turn,
            current_tokens, after_tokens, pruned_count, target_tokens,
        )

        await context.event_emitter.emit(
            context.task_id,
            AgentEventType.CONTEXT_COMPACTING,
            {
                "strategy": "soft_prune",
                "beforeTokens": current_tokens,
                "afterTokens": after_tokens,
                "maxContextTokens": max_tokens,
                "beforeCount": len(messages),
                "afterCount": len(modified_messages),
                "removedCount": 0,
                "prunedToolResults": pruned_count,
                "reason": "watermark_40",
            },
        )

        result: dict = {
            "messages": modified_messages,
            "phase": "context_compacting",
            "context_token_estimate": after_tokens,
            "last_context_strategy": "soft_prune",
        }
        # baseline 在内容被修改后失效
        if pruned_count > 0:
            result["context_token_baseline"] = None
        return result

    # ── Micro-compact ─────────────────────────────────────────

    async def _micro_compact(
        self,
        state: AgentState,
        messages: list,
        current_tokens: int,
        max_tokens: int,
        config: RunnableConfig,
        context: NodeContext,
    ) -> dict:
        """保留 SystemMessage + 最近 10 条，对旧消息摘要压缩"""
        return await self._do_compact(
            state, messages, current_tokens, max_tokens, config, context,
            keep_recent=MICRO_COMPACT_KEEP_RECENT,
            strategy="micro_compact",
            reason="watermark_60",
        )

    # ── Emergency-compact ─────────────────────────────────────

    async def _emergency_compact(
        self,
        state: AgentState,
        messages: list,
        current_tokens: int,
        max_tokens: int,
        config: RunnableConfig,
        context: NodeContext,
    ) -> dict:
        """保留 SystemMessage + 最近 3 条，对旧消息摘要压缩"""
        attempts = state.get("context_compaction_attempts", 0) + 1

        logger.warning(
            "[NODE:context_compact] EMERGENCY_COMPACT | task_id=%s | turn=%d | "
            "attempt=%d | before_tokens=%d",
            context.task_id, context.current_turn, attempts, current_tokens,
        )

        result = await self._do_compact(
            state, messages, current_tokens, max_tokens, config, context,
            keep_recent=EMERGENCY_COMPACT_KEEP_RECENT,
            strategy="emergency_compact",
            reason="context_overflow",
        )
        result["context_compaction_attempts"] = attempts
        result["emergency_compact_requested"] = False
        # 清除 compression_strategy 防止循环触发
        result["compression_strategy"] = None
        return result

    # ── Shared compact logic ──────────────────────────────────

    async def _do_compact(
        self,
        state: AgentState,
        messages: list,
        current_tokens: int,
        max_tokens: int,
        config: RunnableConfig,
        context: NodeContext,
        *,
        keep_recent: int,
        strategy: str,
        reason: str,
    ) -> dict:
        """通用压缩逻辑：摘要旧消息 + RemoveMessage

        保留：
        - 首条 SystemMessage（如果有）
        - 最近 keep_recent 条消息

        对中间的消息（最多 MICRO_COMPACT_SUMMARY_MAX_MSGS 条）做 LLM 摘要，
        其余更旧消息仅 RemoveMessage。
        """
        before_count = len(messages)

        # 识别 SystemMessage
        system_idx = 0 if messages and isinstance(messages[0], SystemMessage) else -1
        preserve_start = system_idx + 1

        # 不足压缩阈值，跳过
        if before_count <= preserve_start + keep_recent + 1:
            logger.info(
                "[NODE:context_compact] COMPACT_SKIP | task_id=%s | turn=%d | "
                "reason=too_few_messages | count=%d",
                context.task_id, context.current_turn, before_count,
            )
            return {
                "phase": "context_compacting",
                "context_token_estimate": current_tokens,
                "last_context_strategy": strategy,
            }

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
        summary_text = await self._generate_summary(
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
            "[NODE:context_compact] %s_COMPLETE | task_id=%s | "
            "before_count=%d | after_count=%d | removed=%d | "
            "before_tokens=%d | after_tokens=%d | summary_length=%d",
            strategy.upper(), context.task_id,
            before_count, after_count, removed_count,
            current_tokens, after_tokens, len(summary_text or ""),
        )

        await context.event_emitter.emit(
            context.task_id,
            AgentEventType.CONTEXT_COMPACTING,
            {
                "strategy": strategy,
                "beforeTokens": current_tokens,
                "afterTokens": after_tokens,
                "maxContextTokens": max_tokens,
                "beforeCount": before_count,
                "afterCount": after_count,
                "removedCount": removed_count,
                "summaryLength": len(summary_text) if summary_text else 0,
                "reason": reason,
            },
        )

        return {
            "messages": result_messages,
            "phase": "context_compacting",
            "context_token_estimate": after_tokens,
            "context_token_baseline": None,
            "context_token_baseline_message_count": 0,
            "last_context_strategy": strategy,
        }

    # ── Summary generation ─────────────────────────────────────

    async def _generate_summary(
        self,
        messages: list,
        max_tokens: int,
        config: RunnableConfig,
        context: NodeContext,
    ) -> str | None:
        """调用 LLM 生成操作连续性摘要

        Returns:
            摘要文本，LLM 不可用/失败时返回 None
        """
        llm = config.get("configurable", {}).get("llm")
        if not llm:
            logger.warning(
                "[NODE:context_compact] LLM_UNAVAILABLE | task_id=%s | "
                "fallback=trim",
                context.task_id,
            )
            return None

        # 构建摘要输入
        summary_parts = []
        total_chars = 0
        summary_budget = min(
            SUMMARY_MAX_INPUT_CHARS,
            int(max_tokens * SUMMARY_MAX_TOKEN_FRACTION * 4),
        )

        for msg in messages:
            if isinstance(msg, (RemoveMessage,)):
                continue
            rendered = render_message(msg)
            if total_chars + len(rendered) > summary_budget:
                remaining = summary_budget - total_chars
                if remaining > 200:
                    summary_parts.append(rendered[:remaining] + "\n...(truncated)")
                break
            summary_parts.append(rendered)
            total_chars += len(rendered)

        if not summary_parts:
            return None

        summary_input = "\n\n".join(summary_parts)

        logger.info(
            "[NODE:context_compact] LLM_SUMMARIZE_INPUT | task_id=%s | turn=%d | "
            "input_length=%d | messages_to_summarize=%d | budget=%d",
            context.task_id, context.current_turn, len(summary_input),
            len(messages), summary_budget,
        )

        try:
            response = await llm.ainvoke([
                SystemMessage(content=_COMPACTION_SUMMARY_PROMPT),
                HumanMessage(
                    content=f"Messages to compact:\n\n{summary_input}"
                ),
            ])
            summary_text = (
                response.content if hasattr(response, "content") else str(response)
            )
            logger.info(
                "[NODE:context_compact] LLM_SUMMARIZE_OUTPUT | task_id=%s | turn=%d | "
                "summary_length=%d",
                context.task_id, context.current_turn, len(summary_text),
            )
            return summary_text
        except Exception as e:
            logger.warning(
                "[NODE:context_compact] LLM_SUMMARIZE_ERROR | task_id=%s | turn=%d | "
                "error=%s | fallback=trim",
                context.task_id, context.current_turn, str(e),
            )
            return None


# 保持向后兼容的实例导出
context_compact_node = ContextCompactNode()
