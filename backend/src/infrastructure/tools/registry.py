"""基础设施层 - 工具注册表实现

管理所有已注册工具，提供工具查找和发现，通过 ExecutionPipeline 执行工具。
"""

import logging
from typing import Optional

from src.domain.entities.tool import (
    RegisteredTool,
    ToolContext,
    ToolDef,
    ToolResult,
)
from src.domain.repositories.tool_registry import IToolRegistry
from src.infrastructure.tools.decorator import get_collected_tools
from src.infrastructure.tools.pipeline import ExecutionPipeline

logger = logging.getLogger(__name__)


class ToolRegistry(IToolRegistry):
    """工具注册表实现

    职责：
    1. 管理所有已注册工具
    2. 提供工具查找和发现
    3. 通过 ExecutionPipeline 执行工具
    """

    def __init__(self, pipeline: Optional[ExecutionPipeline] = None):
        self._tools: dict[str, RegisteredTool] = {}
        self._pipeline = pipeline or ExecutionPipeline()

    def register(self, tool: RegisteredTool) -> None:
        """注册工具"""
        if tool.name in self._tools:
            logger.warning("Tool '%s' already registered, overwriting", tool.name)
        self._tools[tool.name] = tool
        logger.info("Tool registered: %s (category=%s)", tool.name, tool.category)

    def unregister(self, name: str) -> bool:
        """取消注册"""
        if name in self._tools:
            del self._tools[name]
            logger.info("Tool unregistered: %s", name)
            return True
        return False

    def resolve(self, name: str) -> Optional[RegisteredTool]:
        """按名称查找工具"""
        return self._tools.get(name)

    def list_tools(self, category: Optional[str] = None) -> list[RegisteredTool]:
        """列出工具"""
        tools = list(self._tools.values())
        if category:
            tools = [t for t in tools if t.category == category]
        return tools

    def get_tool_defs(self, category: Optional[str] = None) -> list[ToolDef]:
        """获取 ToolDef 列表（供 Prompt Builder Layer 5 使用）"""
        tools = self.list_tools(category)
        return [t.to_tool_def() for t in tools]

    async def execute(
        self,
        name: str,
        input: dict,
        context: Optional[ToolContext] = None,
    ) -> ToolResult:
        """执行工具（经过中间件管道）"""
        tool = self.resolve(name)
        if not tool:
            return ToolResult(
                output=f"Error: Tool '{name}' not found",
                success=False,
                error=f"Tool '{name}' is not registered",
            )

        return await self._pipeline.execute(tool, input, context)

    def auto_register_collected(self) -> None:
        """自动注册所有通过 @tool 装饰器收集的工具"""
        for t in get_collected_tools():
            self.register(t)

    @property
    def tool_count(self) -> int:
        return len(self._tools)
