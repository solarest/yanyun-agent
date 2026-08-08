"""应用层 - SSE 事件服务

职责：
1. 发射事件：生成序列号、构建 DTO、持久化到文件、推送
2. 订阅管理：多客户端订阅同一任务
3. 断线重连：支持 last-event-id 补发
"""

import asyncio
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

from src.application.dtos.event_dto import SSEEventDTO
from src.domain.entities.event_types import AgentEventType
from src.domain.services import IEventEmitter


class StreamEventService(IEventEmitter):
    """SSE 事件服务 — 应用层

    事件持久化到本地文件 (events.jsonl)，同时推送至订阅者队列。
    """

    def __init__(
        self,
        file_storage=None,
        chunk_flush_size: int = 10,
    ):
        self._file_storage = file_storage
        self._task_dirs: Dict[str, Path] = {}
        self._subscribers: Dict[str, List[asyncio.Queue]] = defaultdict(list)
        self._sequences: Dict[str, int] = defaultdict(int)
        self._chunk_buffers: Dict[str, List[SSEEventDTO]] = defaultdict(list)
        self._locks: Dict[str, asyncio.Lock] = {}
        self._chunk_flush_size = chunk_flush_size

    def set_task_dir(self, task_id: str, task_dir: Path) -> None:
        """Register the file storage directory for a task."""
        self._task_dirs[task_id] = task_dir

    def remove_task_dir(self, task_id: str) -> None:
        """Remove the registered task directory (cleanup to prevent memory leak)."""
        self._task_dirs.pop(task_id, None)

    def _get_lock(self, task_id: str) -> asyncio.Lock:
        lock = self._locks.get(task_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[task_id] = lock
        return lock

    async def _save_event(self, task_id: str, event: SSEEventDTO) -> None:
        task_dir = self._task_dirs.get(task_id)
        if task_dir is None:
            return
        if self._file_storage is None:
            return
        self._file_storage.append_event(task_dir, {
            "seq": int(event.id),
            "type": event.event_type,
            "data": event.data,
        })

    async def _save_events(self, task_id: str, events: List[SSEEventDTO]) -> None:
        if not events:
            return
        task_dir = self._task_dirs.get(task_id)
        if task_dir is None:
            return
        if self._file_storage is None:
            return
        for event in events:
            self._file_storage.append_event(task_dir, {
                "seq": int(event.id),
                "type": event.event_type,
                "data": event.data,
            })

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

        task_dir = self._task_dirs.get(task_id)
        if task_dir is None or self._file_storage is None:
            return []

        raw_events = self._file_storage.read_events(task_dir)
        return [
            SSEEventDTO(
                id=str(e["seq"]),
                event_type=e["type"],
                data=e.get("data", {}),
                timestamp=e.get("timestamp", ""),
            ).model_dump_json()
            for e in raw_events
        ]

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

        task_dir = self._task_dirs.get(task_id)
        if task_dir is None or self._file_storage is None:
            return []

        last_seq = int(last_event_id)
        raw_events = self._file_storage.read_events(task_dir, last_event_id=last_seq)
        return [
            SSEEventDTO(
                id=str(e["seq"]),
                event_type=e["type"],
                data=e.get("data", {}),
                timestamp=e.get("timestamp", ""),
            ).model_dump_json()
            for e in raw_events
        ]
