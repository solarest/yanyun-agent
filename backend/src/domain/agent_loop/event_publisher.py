"""领域事件发布器接口 — 用于发布领域事件的抽象。"""

from abc import ABC, abstractmethod

from src.domain.events.base import DomainEvent


class IEventPublisher(ABC):
    """领域事件发布器接口

    用于在领域层发布领域事件，实现方确定交付机制（同步/异步、内存/消息队列等）。
    """

    @abstractmethod
    async def publish(self, event: DomainEvent) -> None:
        """发布领域事件"""
        ...

    @abstractmethod
    async def publish_all(self, events: list[DomainEvent]) -> None:
        """批量发布领域事件"""
        ...
