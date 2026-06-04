"""基础设施层 - 超时控制中间件"""

import asyncio
from typing import Any, Optional

from src.domain.tools import RegisteredTool, ToolContext, ToolResult


class TimeoutMiddleware:
    """超时控制中间件"""

    async def process(
        self,
        tool: RegisteredTool,
        input: dict[str, Any],
        context: Optional[ToolContext],
        next_handler: Any,
    ) -> ToolResult:
        timeout_sec = tool.policy.timeout_ms / 1000.0

        try:
            return await asyncio.wait_for(
                next_handler(tool, input, context),
                timeout=timeout_sec,
            )
        except asyncio.TimeoutError:
            return ToolResult(
                output=f"Tool '{tool.name}' timed out after {tool.policy.timeout_ms}ms",
                success=False,
                error="timeout",
                metadata={"timeout_ms": tool.policy.timeout_ms},
            )
