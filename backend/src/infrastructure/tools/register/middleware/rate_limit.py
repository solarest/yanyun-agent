"""基础设施层 - 限流中间件"""

import time
from collections import defaultdict
from typing import Any, Optional

from src.domain.tools import RegisteredTool, ToolContext, ToolResult


class RateLimitMiddleware:
    """令牌桶限流中间件"""

    def __init__(self, global_max_per_minute: int = 300):
        self._call_records: dict[str, list[float]] = defaultdict(list)
        self._global_max = global_max_per_minute

    async def process(
        self,
        tool: RegisteredTool,
        input: dict[str, Any],
        context: Optional[ToolContext],
        next_handler: Any,
    ) -> ToolResult:
        now = time.time()
        window_start = now - 60.0

        tool_records = self._call_records[tool.name]
        self._call_records[tool.name] = [t for t in tool_records if t > window_start]

        if len(self._call_records[tool.name]) >= tool.policy.max_calls_per_minute:
            return ToolResult(
                output=(
                    f"Tool '{tool.name}' rate limited: "
                    f"max {tool.policy.max_calls_per_minute} calls/min"
                ),
                success=False,
                error="rate_limited",
            )

        self._call_records[tool.name].append(now)
        return await next_handler(tool, input, context)
