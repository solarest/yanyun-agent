"""基础设施层 - 沙箱执行中间件"""

from typing import Any, Optional

from src.domain.tools import RegisteredTool, ToolContext, ToolResult


class SandboxMiddleware:
    """沙箱执行中间件"""

    async def process(
        self,
        tool: RegisteredTool,
        input: dict[str, Any],
        context: Optional[ToolContext],
        next_handler: Any,
    ) -> ToolResult:
        if not tool.policy.sandboxed:
            return await next_handler(tool, input, context)

        result = await next_handler(tool, input, context)
        result.metadata["sandboxed"] = True
        return result
