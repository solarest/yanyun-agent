"""基础设施层 - Team Message Bus 实现

使用 asyncio.Queue 提供进程内消息传递。
每个团队执行实例拥有一个独立的消息总线。
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from src.domain.team.message import TeamMessage
from src.domain.team.message_bus import ITeamMessageBus

logger = logging.getLogger(__name__)


class InProcessTeamMessageBus(ITeamMessageBus):
    """进程内团队消息总线

    使用 asyncio.Queue 为每个 agent 维护一个消息队列。
    Leader ↔ Member 双向通信，Members 之间无法直接通信。
    """

    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue[TeamMessage]] = {}
        self._agent_ids: list[str] = []
        self._shutdown = False

    async def register_agent(self, agent_id: str) -> None:
        """为 agent 注册一个消息队列"""
        if agent_id not in self._queues:
            self._queues[agent_id] = asyncio.Queue()
            self._agent_ids.append(agent_id)
            logger.info("TeamMessageBus: registered agent %s", agent_id)

    async def send(self, message: TeamMessage) -> None:
        """发送消息到目标 agent 的队列"""
        receiver_id = message.receiver_agent_id
        queue = self._queues.get(receiver_id)
        if queue is None:
            logger.warning(
                "TeamMessageBus: receiver %s not registered, message dropped (type=%s)",
                receiver_id, message.message_type,
            )
            return
        await queue.put(message)
        logger.debug(
            "TeamMessageBus: %s → %s [%s]",
            message.sender_agent_id, receiver_id, message.message_type.value,
        )

    async def receive(
        self, agent_id: str, timeout: float | None = None
    ) -> Optional[TeamMessage]:
        """从 agent 的队列接收消息（阻塞，可超时）"""
        queue = self._queues.get(agent_id)
        if queue is None:
            logger.warning("TeamMessageBus: no queue for agent %s", agent_id)
            return None

        try:
            if timeout is not None:
                message = await asyncio.wait_for(queue.get(), timeout=timeout)
            else:
                message = await queue.get()
            message.read_at = datetime.now()
            logger.debug(
                "TeamMessageBus: %s received [%s] from %s",
                agent_id, message.message_type.value, message.sender_agent_id,
            )
            return message
        except asyncio.TimeoutError:
            return None

    async def poll(self, agent_id: str) -> Optional[TeamMessage]:
        """非阻塞轮询 agent 的队列"""
        queue = self._queues.get(agent_id)
        if queue is None or queue.empty():
            return None
        try:
            message = queue.get_nowait()
            message.read_at = datetime.now()
            return message
        except asyncio.QueueEmpty:
            return None

    async def broadcast(self, message: TeamMessage) -> None:
        """向所有已注册 agent 广播消息"""
        for agent_id in self._agent_ids:
            if agent_id != message.sender_agent_id:
                broadcast_msg = TeamMessage(
                    id=message.id,
                    team_id=message.team_id,
                    sender_agent_id=message.sender_agent_id,
                    receiver_agent_id=agent_id,
                    message_type=message.message_type,
                    content=message.content,
                    request_id=message.request_id,
                )
                await self.send(broadcast_msg)

    async def shutdown(self) -> None:
        """关闭消息总线，清理所有队列"""
        self._shutdown = True
        for agent_id, queue in self._queues.items():
            while not queue.empty():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
        self._queues.clear()
        self._agent_ids.clear()
        logger.info("TeamMessageBus: shutdown complete")
