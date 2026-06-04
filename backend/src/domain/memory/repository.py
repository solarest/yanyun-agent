"""记忆子域 - 仓储接口"""

from abc import ABC, abstractmethod
from typing import Optional

from src.domain.memory.entity import MemoryEntry
from src.domain.memory.query import MemoryQuery, MemorySearchResult


class IMemoryRepository(ABC):
    """记忆仓储接口

    定义记忆持久化操作规范，由基础设施层实现。
    """

    @abstractmethod
    async def add(self, entry: MemoryEntry) -> MemoryEntry:
        """新增记忆"""
        ...

    @abstractmethod
    async def get_by_id(self, memory_id: str) -> Optional[MemoryEntry]:
        """根据 ID 获取记忆"""
        ...

    @abstractmethod
    async def search(self, query: MemoryQuery) -> list[MemorySearchResult]:
        """搜索记忆（文本匹配 + 分类/标签筛选）"""
        ...

    @abstractmethod
    async def list_by_agent(
        self,
        agent_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MemoryEntry]:
        """列出 Agent 的所有记忆（分页）"""
        ...

    @abstractmethod
    async def update(self, entry: MemoryEntry) -> MemoryEntry:
        """更新记忆"""
        ...

    @abstractmethod
    async def remove(self, memory_id: str) -> bool:
        """删除记忆"""
        ...

    @abstractmethod
    async def remove_by_agent(self, agent_id: str) -> int:
        """删除 Agent 的所有记忆，返回删除数量"""
        ...

    @abstractmethod
    async def count_by_agent(self, agent_id: str) -> int:
        """统计 Agent 的记忆数量"""
        ...
