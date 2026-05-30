"""应用层 - SSE 事件服务

职责：
1. 发射事件：生成序列号、构建 DTO、持久化、推送
2. 订阅管理：多客户端订阅同一任务
3. 断线重连：支持 last-event-id 补发
"""

import asyncio
from collections import defaultdict
from typing import Any, AsyncContextManager, Callable, Dict, List

from src.application.dtos.event_dto import SSEEventDTO
from src.application.services.event_mapper import EventMapper
from src.domain.entities.event_types import AgentEventType
from src.domain.repositories.event_repository import IEventRepository
from src.domain.services import IEventEmitter


EventRepoFactory = Callable[[], AsyncContextManager[IEventRepository]]


class StreamEventService(IEventEmitter):
    """SSE 事件服务 — 应用层"""

    def __init__(self, event_repo_factory: EventRepoFactory, chunk_flush_size: int = 10):
        self._event_repo_factory = event_repo_factory
        self._subscribers: Dict[str, List[asyncio.Queue]] = defaultdict(list)
        self._sequences: Dict[str, int] = defaultdict(int)
        self._chunk_buffers: Dict[str, List[SSEEventDTO]] = defaultdict(list)
        self._locks: Dict[str, asyncio.Lock] = {}
        self._chunk_flush_size = chunk_flush_size

    def _get_lock(self, task_id: str) -> asyncio.Lock:
        lock = self._locks.get(task_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[task_id] = lock
        return lock

    async def _save_event(self, task_id: str, event: SSEEventDTO) -> None:
        # 将 DTO 转换为领域实体后保存
        entity = EventMapper.to_entity(event)
        async with self._event_repo_factory() as event_repo:
            await event_repo.save(task_id, entity)

    async def _save_events(self, task_id: str, events: List[SSEEventDTO]) -> None:
        if not events:
            return
        # 将 DTO 列表转换为领域实体列表后保存
        entities = EventMapper.to_entity_list(events)
        async with self._event_repo_factory() as event_repo:
            await event_repo.save_batch(task_id, entities)

    async def _flush_chunks_locked(self, task_id: str) -> None:
        buffered = self._chunk_buffers.get(task_id, [])
        if not buffered:
            return

        chunks = list(buffered)
        self._chunk_buffers[task_id].clear()
        await self._save_events(task_id, chunks)

    async def emit(self, task_id: str, event_type: str, payload: Dict[str, Any]) -> None:
        """发射事件 — 从任何 Node 或 UseCase 调用

        Args:
            task_id: 任务 ID
            event_type: 事件类型 (如 AgentEventType.LLM_CHUNK, AgentEventType.TOOL_RESULT)
            payload: 事件载荷
        """
        async with self._get_lock(task_id):
            self._sequences[task_id] += 1
            seq = self._sequences[task_id]

            event = SSEEventDTO.create(task_id, seq, event_type, payload)

            if event.event_type == AgentEventType.LLM_CHUNK:
                self._chunk_buffers[task_id].append(event)
                if len(self._chunk_buffers[task_id]) >= self._chunk_flush_size:
                    await self._flush_chunks_locked(task_id)
            else:
                await self._flush_chunks_locked(task_id)
                await self._save_event(task_id, event)

        event_json = event.model_dump_json()
        for queue in list(self._subscribers.get(task_id, [])):
            await queue.put(event_json)

    async def emit_phase_changed(
        self,
        task_id: str,
        new_phase: str,
        previous_phase: str,
        turn: int,
    ) -> None:
        """发射阶段变更事件。"""
        await self.emit(
            task_id,
            AgentEventType.PHASE_CHANGED,
            {
                "phase": new_phase,
                "previousPhase": previous_phase,
                "turn": turn,
            },
        )

    async def emit_llm_chunk(
        self,
        task_id: str,
        turn: int,
        text: str,
    ) -> None:
        """发射流式输出片段。"""
        await self.emit(
            task_id,
            AgentEventType.LLM_CHUNK,
            {
                "turn": turn,
                "text": text,
                "delta": True,
            },
        )

    async def emit_thinking_chunk(
        self,
        task_id: str,
        turn: int,
        text: str,
    ) -> None:
        """发射深度思考流式输出片段。"""
        await self.emit(
            task_id,
            AgentEventType.THINKING_CHUNK,
            {
                "turn": turn,
                "text": text,
                "delta": True,
            },
        )

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

    async def get_all_events(self, task_id: str) -> List[str]:
        """获取任务的所有事件 (SSE 首次连接回放)

        Args:
            task_id: 任务 ID

        Returns:
            事件 JSON 字符串列表
        """
        async with self._get_lock(task_id):
            await self._flush_chunks_locked(task_id)
            async with self._event_repo_factory() as event_repo:
                events = await event_repo.get_by_task_id(task_id)
        # 将领域实体转换为 DTO，然后序列化
        dtos = EventMapper.to_dto_list(events)
        return [dto.model_dump_json() for dto in dtos]

    async def get_events_after(self, task_id: str, last_event_id: str) -> List[str]:
        """获取指定序列号之后的事件 (断线重连补发)

        Args:
            task_id: 任务 ID
            last_event_id: 最后接收的事件 ID

        Returns:
            事件 JSON 字符串列表
        """
        async with self._get_lock(task_id):
            await self._flush_chunks_locked(task_id)
            async with self._event_repo_factory() as event_repo:
                events = await event_repo.get_after(task_id, last_event_id)
        # 将领域实体转换为 DTO，然后序列化
        dtos = EventMapper.to_dto_list(events)
        return [dto.model_dump_json() for dto in dtos]
