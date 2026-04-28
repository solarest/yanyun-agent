"""基础设施层 - 安全检查中间件

职责：
1. 检查工具是否在白名单中（如果启用白名单）
2. 验证文件路径是否在允许范围内
3. 检查是否需要审批
"""

import os
from typing import Any, Optional

from src.domain.entities.tool import RegisteredTool, ToolContext, ToolResult


class SecurityMiddleware:
    """安全检查中间件"""

    def __init__(self, allowed_tools: Optional[list[str]] = None):
        self._allowed_tools = allowed_tools  # None 表示不限制

    async def process(
        self,
        tool: RegisteredTool,
        input: dict[str, Any],
        context: Optional[ToolContext],
        next_handler: Any,
    ) -> ToolResult:
        # 白名单检查
        if self._allowed_tools is not None and tool.name not in self._allowed_tools:
            return ToolResult(
                output=f"Tool '{tool.name}' is not allowed in current context",
                success=False,
                error="permission_denied",
            )

        # 文件路径安全检查（file 类工具）
        if tool.category == "file" and tool.policy.allowed_paths:
            path = input.get("path", "") or input.get("file_path", "")
            if path and not self._is_path_allowed(path, list(tool.policy.allowed_paths)):
                return ToolResult(
                    output=f"Access denied: path '{path}' is outside allowed directories",
                    success=False,
                    error="path_not_allowed",
                )

        # 审批检查（需要 HITL 支持）
        if tool.policy.requires_approval:
            # TODO: 集成 HITL 审批流程
            pass

        return await next_handler(tool, input, context)

    @staticmethod
    def _is_path_allowed(path: str, allowed_paths: list[str]) -> bool:
        """检查路径是否在允许的目录下"""
        abs_path = os.path.abspath(path)
        return any(abs_path.startswith(os.path.abspath(p)) for p in allowed_paths)
