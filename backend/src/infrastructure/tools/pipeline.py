"""基础设施层 - 工具执行管道

洋葱模型中间件链：Security -> RateLimit -> Timeout -> Sandbox -> Invoke
"""

import logging
import time
from typing import Any, Optional, Protocol

from src.domain.tool import RegisteredTool, ToolContext, ToolResult

logger = logging.getLogger(__name__)


class Middleware(Protocol):
    """中间件协议"""

    async def process(
        self,
        tool: RegisteredTool,
        input: dict[str, Any],
        context: Optional[ToolContext],
        next_handler: Any,
    ) -> ToolResult: ...


class ExecutionPipeline:
    """工具执行管道

    按顺序执行中间件链：Security -> RateLimit -> Timeout -> Sandbox -> Invoke
    """

    def __init__(self, middlewares: Optional[list[Middleware]] = None):
        self._middlewares: list[Middleware] = middlewares or []

    def add_middleware(self, middleware: Middleware) -> None:
        """添加中间件"""
        self._middlewares.append(middleware)

    async def execute(
        self,
        tool: RegisteredTool,
        input: dict[str, Any],
        context: Optional[ToolContext] = None,
    ) -> ToolResult:
        """执行工具（经过中间件链）"""
        start_time = time.time()

        # 构建中间件链（洋葱模型）
        async def final_handler(
            t: RegisteredTool,
            inp: dict[str, Any],
            ctx: Optional[ToolContext],
        ) -> ToolResult:
            return await t.func(inp, ctx)

        handler = final_handler
        for mw in reversed(self._middlewares):
            handler = _make_next(mw, handler)

        try:
            result = await handler(tool, input, context)
            duration_ms = int((time.time() - start_time) * 1000)
            result.metadata["duration_ms"] = duration_ms
            logger.info(
                "Tool executed: %s",
                tool.name,
                extra={
                    "tool": tool.name,
                    "duration_ms": duration_ms,
                    "success": result.success,
                },
            )
            return result
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Tool execution failed: %s",
                tool.name,
                extra={
                    "tool": tool.name,
                    "error": str(e),
                    "duration_ms": duration_ms,
                },
            )
            return ToolResult(
                output=f"Tool execution error: {e}",
                success=False,
                error=str(e),
                metadata={"duration_ms": duration_ms},
            )


def _make_next(mw: Middleware, next_handler: Any) -> Any:
    """构建洋葱模型中间件调用链"""

    async def handler(
        tool: RegisteredTool,
        input: dict[str, Any],
        context: Optional[ToolContext],
    ) -> ToolResult:
        return await mw.process(tool, input, context, next_handler)

    return handler
