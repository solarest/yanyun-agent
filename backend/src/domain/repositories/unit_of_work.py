"""领域层 - 工作单元接口 (Unit of Work)

确保跨聚合操作的原子性。由基础设施层提供事务实现。
"""

from abc import ABC, abstractmethod
from typing import Any


class IUnitOfWork(ABC):
    """工作单元接口

    管理仓储访问和事务边界。所有在同一 UoW 内的仓储操作共享同一事务。
    """

    @abstractmethod
    async def __aenter__(self) -> "IUnitOfWork":
        ...

    @abstractmethod
    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        ...

    @property
    @abstractmethod
    def agents(self) -> Any:
        """Agent 仓储"""
        ...

    @property
    @abstractmethod
    def tasks(self) -> Any:
        """Task 仓储"""
        ...

    @property
    @abstractmethod
    def sessions(self) -> Any:
        """Session 仓储"""
        ...

    @property
    @abstractmethod
    def session_messages(self) -> Any:
        """SessionMessage 仓储"""
        ...

    @property
    @abstractmethod
    def skills(self) -> Any:
        """Skill 仓储"""
        ...

    @abstractmethod
    async def commit(self) -> None:
        """提交事务"""
        ...

    @abstractmethod
    async def rollback(self) -> None:
        """回滚事务"""
        ...
