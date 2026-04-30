"""领域层 - EventRepository 接口"""

from abc import ABC, abstractmethod
from typing import List

from src.application.dtos.event_dto import SSEEventDTO


class IEventRepository(ABC):
    """事件仓储接口"""

    @abstractmethod
    async def save(self, task_id: str, event: SSEEventDTO) -> None:
        """保存事件"""
        pass

    @abstractmethod
    async def save_batch(self, task_id: str, events: List[SSEEventDTO]) -> None:
        """批量保存事件"""
        pass

    @abstractmethod
    async def get_after(self, task_id: str, last_event_id: str) -> List[SSEEventDTO]:
        """获取指定序列号之后的事件 (断线重连补发)"""
        pass

    @abstractmethod
    async def get_by_task_id(self, task_id: str) -> List[SSEEventDTO]:
        """获取任务的所有事件"""
        pass
