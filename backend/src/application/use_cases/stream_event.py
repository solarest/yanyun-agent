"""应用层 - SSE 事件服务

职责：
1. 发射事件：生成序列号、构建 DTO、持久化、推送
2. 订阅管理：多客户端订阅同一任务
3. 断线重连：支持 last-event-id 补发
"""

import asyncio
from collections import defaultdict
from typing import Any, Dict, List

from src.application.dtos.event_dto import SSEEventDTO
from src.domain.repositories.event_repository import IEventRepository


class StreamEventService:
    """SSE 事件服务 — 应用层"""

    def __init__(self, event_repo: IEventRepository):
        self.event_repo = event_repo
        self._subscribers: Dict[str, List[asyncio.Queue]] = defaultdict(list)
        self._sequences: Dict[str, int] = defaultdict(int)

    async def emit(self, task_id: str, event_type: str, payload: Dict[str, Any]) -> None:
        """发射事件 — 从任何 Node 或 UseCase 调用

        Args:
            task_id: 任务 ID
            event_type: 事件类型 (如 "llm:chunk", "tool:result")
            payload: 事件载荷
        """
        self._sequences[task_id] += 1
        seq = self._sequences[task_id]

        event = SSEEventDTO.create(task_id, seq, event_type, payload)

        # 1. 持久化 (支持断线重连)
        await self.event_repo.save(task_id, event)

        # 2. 推送给所有订阅者
        for queue in self._subscribers.get(task_id, []):
            await queue.put(event.model_dump_json())

    async def subscribe(self, task_id: str) -> asyncio.Queue:
        """订阅任务事件流

        Args:
            task_id: 任务 ID

        Returns:
            事件队列
        """
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers[task_id].append(queue)
        return queue

    async def unsubscribe(self, task_id: str, queue: asyncio.Queue) -> None:
        """取消订阅

        Args:
            task_id: 任务 ID
            queue: 要取消的队列
        """
        if task_id in self._subscribers:
            self._subscribers[task_id].remove(queue)
            if not self._subscribers[task_id]:
                del self._subscribers[task_id]

    async def get_events_after(self, task_id: str, last_event_id: str) -> List[str]:
        """获取指定序列号之后的事件 (断线重连补发)

        Args:
            task_id: 任务 ID
            last_event_id: 最后接收的事件 ID

        Returns:
            事件 JSON 字符串列表
        """
        events = await self.event_repo.get_after(task_id, last_event_id)
        return [e.model_dump_json() for e in events]
