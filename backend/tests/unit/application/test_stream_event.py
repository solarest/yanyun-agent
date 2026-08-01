"""Tests for StreamEventService and ProxyEventEmitter."""

import json

import pytest

from src.application.agent_loop.stream_event import StreamEventService
from src.application.services.session_file_storage import SessionFileStorage
from src.domain.entities.event_types import AgentEventType
from src.domain.services.event_emitter import ProxyEventEmitter


@pytest.fixture
def file_storage_and_dir(tmp_path):
    storage = SessionFileStorage(base_path=str(tmp_path / "sessions"))
    session_id = "sess-test"
    task_id = "task-test"
    task_dir = storage.create_task_dir(session_id, task_id)
    return storage, task_dir, task_id


@pytest.mark.asyncio
async def test_stream_event_service_normalizes_events_and_flushes_on_replay(
    file_storage_and_dir,
) -> None:
    storage, task_dir, task_id = file_storage_and_dir
    service = StreamEventService(
        file_storage=storage, chunk_flush_size=5)
    service.set_task_dir(task_id, task_dir)

    await service.emit(task_id, "task:started", {})
    await service.emit_llm_chunk(task_id, 1, "Hel")
    await service.emit_llm_chunk(task_id, 1, "lo")

    all_events = [json.loads(item) for item in await service.get_all_events(task_id)]
    assert [event["event_type"] for event in all_events] == [
        "task:started",
        AgentEventType.LLM_CHUNK,
        AgentEventType.LLM_CHUNK,
    ]

    replayed = [json.loads(item) for item in await service.get_events_after(task_id, "1")]
    assert [event["id"] for event in replayed] == ["2", "3"]


@pytest.mark.asyncio
async def test_non_chunk_event_flushes_chunk_buffer_before_cancelled_terminal_event(
    file_storage_and_dir,
) -> None:
    storage, task_dir, task_id = file_storage_and_dir
    service = StreamEventService(
        file_storage=storage, chunk_flush_size=10)
    service.set_task_dir(task_id, task_dir)

    await service.emit_llm_chunk(task_id, 2, "A")
    await service.emit_llm_chunk(task_id, 2, "B")
    await service.emit(task_id, AgentEventType.TASK_CANCELLED, {})

    all_events = [json.loads(item) for item in await service.get_all_events(task_id)]
    event_types = [event["event_type"] for event in all_events]
    assert event_types == [
        AgentEventType.LLM_CHUNK,
        AgentEventType.LLM_CHUNK,
        AgentEventType.TASK_CANCELLED,
    ]


class RecordingEmitter:
    def __init__(self) -> None:
        self.events = []

    async def emit(self, task_id: str, event_type: str, payload: dict) -> None:
        self.events.append((task_id, event_type, payload))

    async def emit_phase_changed(
        self,
        task_id: str,
        new_phase: str,
        previous_phase: str,
        turn: int,
    ) -> None:
        await self.emit(
            task_id,
            AgentEventType.PHASE_CHANGED,
            {"phase": new_phase, "previousPhase": previous_phase, "turn": turn},
        )

    async def emit_llm_chunk(self, task_id: str, turn: int, text: str) -> None:
        await self.emit(task_id, AgentEventType.LLM_CHUNK, {"turn": turn, "text": text})

    async def emit_thinking_chunk(self, task_id: str, turn: int, text: str) -> None:
        await self.emit(task_id, AgentEventType.THINKING_CHUNK, {"turn": turn, "text": text})


@pytest.mark.asyncio
async def test_proxy_event_emitter_writes_to_parent_stream_with_sub_task_marker() -> None:
    parent = RecordingEmitter()
    proxy = ProxyEventEmitter(
        parent,
        parent_task_id="parent-task-1",
        sub_task_id="sub-task-1",
    )

    await proxy.emit("sub-task-1", AgentEventType.TASK_STARTED, {})
    await proxy.emit_llm_chunk("sub-task-1", 1, "hello")

    assert parent.events == [
        ("parent-task-1", AgentEventType.TASK_STARTED,
         {"sub_task_id": "sub-task-1"}),
        (
            "parent-task-1",
            AgentEventType.LLM_CHUNK,
            {"turn": 1, "text": "hello", "delta": True, "sub_task_id": "sub-task-1"},
        ),
    ]
