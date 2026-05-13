"""领域层 - EventRepository 接口"""

from abc import ABC, abstractmethod
from typing import List

from src.domain.entities.event import Event


class IEventRepository(ABC):
    """事件仓储接口"""

    @abstractmethod
    async def save(self, task_id: str, event: Event) -> None:
        """保存事件"""
        pass

    @abstractmethod
    async def save_batch(self, task_id: str, events: List[Event]) -> None:
        """批量保存事件"""
        pass

    @abstractmethod
    async def get_after(self, task_id: str, last_event_id: str) -> List[Event]:
        """获取指定序列号之后的事件 (断线重连补发)"""
        pass

    @abstractmethod
    async def get_by_task_id(self, task_id: str) -> List[Event]:
        """获取任务的所有事件"""
        pass
