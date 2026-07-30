"""LLM 摘要生成器 — 从 ContextCompactNode._generate_summary() 抽取

独立的 SummaryGenerator 类，供各压缩策略通过组合使用。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage, SystemMessage

from src.domain.services.token_utils import render_message

if TYPE_CHECKING:
    from langgraph.types import RunnableConfig
    from src.infrastructure.agent.nodes.base_node import NodeContext

logger = logging.getLogger(__name__)

# ── 任务聚焦摘要 Prompt ───────────────────────────────────────

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

# ── 常量 ─────────────────────────────────────────────────────

SUMMARY_MAX_INPUT_CHARS = 32000
SUMMARY_MAX_TOKEN_FRACTION = 0.05


class SummaryGenerator:
    """LLM 上下文摘要生成器

    封装 LLM 调用以生成操作连续性摘要。
    LLM 不可用/失败时返回 None，调用方应降级为纯 RemoveMessage (trim)。
    """

    def __init__(
        self,
        summary_prompt: str = _COMPACTION_SUMMARY_PROMPT,
        max_input_chars: int = SUMMARY_MAX_INPUT_CHARS,
        max_token_fraction: float = SUMMARY_MAX_TOKEN_FRACTION,
    ):
        self.summary_prompt = summary_prompt
        self.max_input_chars = max_input_chars
        self.max_token_fraction = max_token_fraction

    async def generate(
        self,
        messages: list,
        max_tokens: int,
        config: RunnableConfig,
        context: NodeContext,
    ) -> str | None:
        """调用 LLM 生成操作连续性摘要

        Args:
            messages: 待摘要的消息列表
            max_tokens: 上下文窗口 Token 上限
            config: LangGraph 配置 (从中获取 llm)
            context: 节点执行上下文

        Returns:
            摘要文本，LLM 不可用/失败时返回 None
        """
        llm = config.get("configurable", {}).get("llm")
        if not llm:
            logger.warning(
                "[compaction:SummaryGenerator] LLM_UNAVAILABLE | task_id=%s | "
                "fallback=trim",
                context.task_id,
            )
            return None

        # 构建摘要输入
        summary_parts = []
        total_chars = 0
        summary_budget = min(
            self.max_input_chars,
            int(max_tokens * self.max_token_fraction * 4),
        )

        from langchain_core.messages import RemoveMessage

        for msg in messages:
            if isinstance(msg, RemoveMessage):
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
            "[compaction:SummaryGenerator] LLM_SUMMARIZE_INPUT | task_id=%s | "
            "turn=%d | input_length=%d | messages_to_summarize=%d | budget=%d",
            context.task_id, context.current_turn, len(summary_input),
            len(messages), summary_budget,
        )

        try:
            response = await llm.ainvoke([
                SystemMessage(content=self.summary_prompt),
                HumanMessage(
                    content=f"Messages to compact:\n\n{summary_input}"
                ),
            ])
            summary_text = (
                response.content if hasattr(response, "content") else str(response)
            )
            logger.info(
                "[compaction:SummaryGenerator] LLM_SUMMARIZE_OUTPUT | task_id=%s | "
                "turn=%d | summary_length=%d",
                context.task_id, context.current_turn, len(summary_text),
            )
            return summary_text
        except Exception as e:
            logger.warning(
                "[compaction:SummaryGenerator] LLM_SUMMARIZE_ERROR | task_id=%s | "
                "turn=%d | error=%s | fallback=trim",
                context.task_id, context.current_turn, str(e),
            )
            return None
