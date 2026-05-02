"""领域层 - 工具注册表接口

定义工具注册、发现和执行的抽象接口。
遵循 DDD 原则：接口在领域层，实现在基础设施层。
"""

from abc import ABC, abstractmethod
from typing import Optional

from src.domain.entities.tool import (
    RegisteredTool,
    ToolContext,
    ToolDef,
    ToolResult,
)


class IToolRegistry(ABC):
    """工具注册表接口"""

    @abstractmethod
    def register(self, tool: RegisteredTool) -> None:
        """注册一个工具"""
        ...

    @abstractmethod
    def unregister(self, name: str) -> bool:
        """取消注册一个工具"""
        ...

    @abstractmethod
    def resolve(self, name: str) -> Optional[RegisteredTool]:
        """按名称查找工具"""
        ...

    @abstractmethod
    def list_tools(self, category: Optional[str] = None) -> list[RegisteredTool]:
        """列出所有已注册工具（可按分类筛选）"""
        ...

    @abstractmethod
    def get_tool_defs(self, category: Optional[str] = None) -> list[ToolDef]:
        """获取所有工具的 ToolDef 定义（用于 Prompt Builder）"""
        ...

    @abstractmethod
    async def execute(
        self,
        name: str,
        input: dict,
        context: Optional[ToolContext] = None,
    ) -> ToolResult:
        """执行指定工具"""
        ...
