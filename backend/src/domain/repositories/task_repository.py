"""领域层 - TaskRepository 接口"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from src.domain.aggregates.task.task import Task


class ITaskRepository(ABC):
    """任务仓储接口"""

    @abstractmethod
    async def get_by_id(self, task_id: str) -> Optional[Task]:
        """根据 ID 获取任务"""
        pass

    @abstractmethod
    async def add(self, task: Task) -> Task:
        """添加任务"""
        pass

    @abstractmethod
    async def update(self, task: Task) -> Task:
        """更新任务"""
        pass

    @abstractmethod
    async def remove(self, task_id: str) -> bool:
        """删除任务"""
        pass

    @abstractmethod
    async def list_all(self, limit: int = 100, offset: int = 0) -> List[Task]:
        """获取任务列表"""
        pass
