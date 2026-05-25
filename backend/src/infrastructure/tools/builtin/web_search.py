"""基础设施层 - 网络搜索工具

默认使用 Tavily 作为搜索提供商。
Tavily 是专为 LLM/AI Agent 设计的搜索 API，返回结构化内容 + 可选 AI 摘要。
"""

import asyncio
import logging
import os
from typing import Any, Optional

from src.domain.entities.tool import ToolContext, ToolResult
from src.infrastructure.tools.decorator import tool

logger = logging.getLogger(__name__)


@tool(
    name="web_search",
    description="Search the internet for real-time information. Use when you need to find the latest news, verify facts, or look up uncertain knowledge.",
    category="web_search",
    returns="Search result list with titles, snippets, source links, and optional AI summary",
    timeout_ms=15000,
    max_calls_per_minute=20,
)
async def web_search(
    query: str,
    max_results: int = 5,
    search_depth: str = "basic",
    include_domains: Optional[list[str]] = None,
    exclude_domains: Optional[list[str]] = None,
    context: Optional[ToolContext] = None,
) -> ToolResult:
    """网络搜索工具（默认使用 Tavily）

    Args:
        query: 搜索关键词或问题
        max_results: 最大返回结果数量（1-10）
        search_depth: 检索深度，basic（快速）或 advanced（更全面但更慢更贵）
        include_domains: 仅在这些域名中搜索（可选）
        exclude_domains: 排除这些域名（可选）
    """
    if not query.strip():
        return ToolResult(
            output="Error: query cannot be empty",
            success=False,
            error="invalid_input",
        )

    max_results = max(1, min(10, max_results))
    if search_depth not in ("basic", "advanced"):
        search_depth = "basic"

    provider = os.getenv("SEARCH_PROVIDER", "tavily").lower()

    try:
        if provider == "tavily":
            payload = await _tavily_search(
                query=query,
                max_results=max_results,
                search_depth=search_depth,
                include_domains=include_domains,
                exclude_domains=exclude_domains,
            )
            formatted = _format_tavily_results(payload)
            return ToolResult(
                output=formatted,
                metadata={
                    "provider": "tavily",
                    "result_count": len(payload.get("results", [])),
                    "has_answer": bool(payload.get("answer")),
                    "search_depth": search_depth,
                },
            )
        else:
            return ToolResult(
                output=f"Unsupported search provider: {provider}",
                success=False,
                error="unsupported_provider",
            )
    except _TavilyConfigError as e:
        logger.error("Tavily config error: %s", e)
        return ToolResult(
            output=f"Search not configured: {e}",
            success=False,
            error="config_missing",
        )
    except Exception as e:
        logger.exception("Web search failed")
        return ToolResult(
            output=f"Search failed: {e}",
            success=False,
            error=str(e),
        )


# ---------------------------------------------------------------------------
# Tavily 提供商实现
# ---------------------------------------------------------------------------


class _TavilyConfigError(Exception):
    """Tavily 配置错误（如缺少 API Key）"""


async def _tavily_search(
    query: str,
    max_results: int,
    search_depth: str,
    include_domains: Optional[list[str]],
    exclude_domains: Optional[list[str]],
) -> dict[str, Any]:
    """调用 Tavily API 执行搜索

    使用官方 SDK tavily-python，其 client.search 为同步调用，
    通过 asyncio.to_thread 包装避免阻塞事件循环。
    """
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise _TavilyConfigError("TAVILY_API_KEY is not set")

    try:
        from tavily import TavilyClient
    except ImportError as e:
        raise _TavilyConfigError("tavily-python not installed. Run: uv add tavily-python") from e

    include_answer = os.getenv("TAVILY_INCLUDE_ANSWER", "true").lower() == "true"

    def _call() -> dict[str, Any]:
        client = TavilyClient(api_key=api_key)
        return client.search(
            query=query,
            max_results=max_results,
            search_depth=search_depth,
            include_answer=include_answer,
            include_domains=include_domains or None,
            exclude_domains=exclude_domains or None,
        )

    return await asyncio.to_thread(_call)


def _format_tavily_results(payload: dict[str, Any]) -> str:
    """将 Tavily 返回格式化为 LLM 可读文本"""
    results = payload.get("results", []) or []
    answer = payload.get("answer")

    if not results and not answer:
        return "No results found."

    parts: list[str] = []

    if answer:
        parts.append("## Summary")
        parts.append(answer.strip())
        parts.append("")

    parts.append("## Search Results")
    for i, r in enumerate(results, 1):
        title = r.get("title") or "Untitled"
        url = r.get("url", "")
        content = (r.get("content") or "").strip()
        score = r.get("score")

        parts.append(f"{i}. **{title}**")
        if url:
            parts.append(f"   URL: {url}")
        if content:
            snippet = content if len(content) <= 500 else content[:500] + "..."
            parts.append(f"   {snippet}")
        if score is not None:
            parts.append(f"   Relevance: {score:.2f}")
        parts.append("")

    return "\n".join(parts).rstrip()
