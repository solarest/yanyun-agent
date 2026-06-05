"""领域层 - Team Message Bus 接口"""

from abc import ABC, abstractmethod
from typing import Optional

from src.domain.team.message import TeamMessage


class ITeamMessageBus(ABC):
    """团队消息总线接口

    负责 Leader ↔ Member 之间的异步消息传递。
    每个团队执行实例拥有一个独立的消息总线，通过 asyncio.Queue 实现。
    """

    @abstractmethod
    async def register_agent(self, agent_id: str) -> None:
        """为 agent 注册一个消息队列"""
        ...

    @abstractmethod
    async def send(self, message: TeamMessage) -> None:
        """发送消息到目标 agent 的队列"""
        ...

    @abstractmethod
    async def receive(self, agent_id: str, timeout: float | None = None) -> Optional[TeamMessage]:
        """从 agent 的队列接收消息（阻塞，可超时）

        Args:
            agent_id: 接收方 agent ID
            timeout: 超时秒数，None 表示无限等待

        Returns:
            消息实体，超时返回 None
        """
        ...

    @abstractmethod
    async def poll(self, agent_id: str) -> Optional[TeamMessage]:
        """非阻塞轮询 agent 的队列

        Returns:
            消息实体，队列为空返回 None
        """
        ...

    @abstractmethod
    async def broadcast(self, message: TeamMessage) -> None:
        """向所有已注册 agent 广播消息"""
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        """关闭消息总线，清理所有队列"""
        ...
