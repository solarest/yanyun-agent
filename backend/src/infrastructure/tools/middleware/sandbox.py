"""基础设施层 - 沙箱执行中间件

对标记为 sandboxed=True 的工具，在受限环境中执行。
Phase 1 实现为标记穿透 + 资源限制预留接口。
"""

from typing import Any, Optional

from src.domain.entities.tool import RegisteredTool, ToolContext, ToolResult


class SandboxMiddleware:
    """沙箱执行中间件

    当前阶段：直接执行 + metadata 标记。
    后续可扩展为 subprocess + seccomp 或 Docker 隔离。
    """

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
