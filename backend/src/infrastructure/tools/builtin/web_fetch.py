"""基础设施层 - 网页内容获取工具

用于获取指定 URL 的 HTML 内容，支持基本的网页抓取功能。
"""

import asyncio
import logging
from typing import Optional
from urllib.parse import urlparse

import httpx

from src.domain.entities.tool import ToolContext, ToolResult
from src.infrastructure.tools.decorator import tool

logger = logging.getLogger(__name__)


@tool(
    name="web_fetch",
    description="Fetch HTML content from a specified URL. Use when you need to analyze webpage structure, extract specific information, or obtain page source.",
    category="web_search",
    returns="HTML content of the webpage, may be truncated to control size",
    timeout_ms=30000,
    max_calls_per_minute=10,
)
async def web_fetch(
    url: str,
    max_length: int = 10000,
    include_headers: bool = False,
    context: Optional[ToolContext] = None,
) -> ToolResult:
    """网页内容获取工具

    Args:
        url: 要获取内容的网页 URL
        max_length: 返回的最大字符数（默认 10000）
        include_headers: 是否返回响应头信息
    """
    if not url.strip():
        return ToolResult(
            output="Error: URL cannot be empty",
            success=False,
            error="invalid_input",
        )

    # 验证 URL 格式
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return ToolResult(
                output=f"Error: Invalid URL format: {url}. Please provide a complete URL with scheme (http/https)",
                success=False,
                error="invalid_url",
            )

        if parsed.scheme not in ('http', 'https'):
            return ToolResult(
                output=f"Error: Only HTTP and HTTPS schemes are supported, got: {parsed.scheme}",
                success=False,
                error="unsupported_scheme",
            )
    except Exception as e:
        return ToolResult(
            output=f"Error: Failed to parse URL: {str(e)}",
            success=False,
            error="invalid_url",
        )

    max_length = max(1000, min(50000, max_length))  # 限制在合理范围内

    try:
        html_content = await _fetch_url(url, max_length)

        output_parts = [
            f"URL: {url}", f"Content Length: {len(html_content)} characters"]
        if include_headers:
            output_parts.append(
                "Headers information would be included here if implemented")

        output_parts.append("")
        output_parts.append("HTML Content:")
        output_parts.append(html_content)

        return ToolResult(
            output="\n".join(output_parts),
            metadata={
                "url": url,
                "content_length": len(html_content),
                "truncated": len(html_content) >= max_length,
            },
        )
    except asyncio.TimeoutError:
        return ToolResult(
            output=f"Error: Request to {url} timed out",
            success=False,
            error="timeout",
        )
    except httpx.HTTPError as e:
        return ToolResult(
            output=f"Error: Failed to fetch URL: {str(e)}",
            success=False,
            error="network_error",
        )
    except Exception as e:
        return ToolResult(
            output=f"Error: Unexpected error occurred: {str(e)}",
            success=False,
            error="unexpected_error",
        )


async def _fetch_url(url: str, max_length: int) -> str:
    """异步获取网页内容

    Args:
        url: 网页 URL
        max_length: 最大返回长度

    Returns:
        网页 HTML 内容（可能被截断）
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'identity',  # 不使用压缩，简化处理
    }

    timeout = httpx.Timeout(25.0)  # 25秒超时

    async with httpx.AsyncClient(headers=headers, timeout=timeout) as client:
        response = await client.get(url)

        # 检查响应状态
        if response.status_code != 200:
            raise httpx.HTTPStatusError(
                f"HTTP {response.status_code}: {response.reason_phrase}",
                request=response.request,
                response=response,
            )

        # 读取文本内容
        content = response.text

        # 截断内容以符合最大长度要求
        if len(content) > max_length:
            content = content[:max_length] + "\n... [Content truncated]"

        return content
