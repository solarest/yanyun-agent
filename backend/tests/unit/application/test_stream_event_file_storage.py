"""Tests for StreamEventService with file-backed storage."""

import json

import pytest

from src.application.agent_loop.stream_event import StreamEventService
from src.application.services.session_file_storage import SessionFileStorage
from src.domain.entities.event_types import AgentEventType


@pytest.fixture
def storage_and_dir(tmp_path):
    """Create a SessionFileStorage + task directory for testing."""
    storage = SessionFileStorage(base_path=str(tmp_path / "sessions"))
    session_id = "sess-test"
    task_id = "task-test"
    task_dir = storage.create_task_dir(session_id, task_id)
    return storage, task_dir, task_id


@pytest.mark.asyncio
async def test_emit_writes_to_events_jsonl(storage_and_dir):
    """Events should be written to events.jsonl instead of DB."""
    storage, task_dir, task_id = storage_and_dir

    service = StreamEventService(file_storage=storage)
    service.set_task_dir(task_id, task_dir)

    await service.emit(task_id, AgentEventType.TASK_STARTED, {})

    events = storage.read_events(task_dir)
    assert len(events) == 1
    assert events[0]["type"] == AgentEventType.TASK_STARTED


@pytest.mark.asyncio
async def test_llm_chunks_buffered_and_flushed(storage_and_dir):
    """LLM chunks should be buffered and flushed in batches."""
    storage, task_dir, task_id = storage_and_dir

    service = StreamEventService(file_storage=storage, chunk_flush_size=3)
    service.set_task_dir(task_id, task_dir)

    await service.emit_llm_chunk(task_id, 1, "Hel")
    await service.emit_llm_chunk(task_id, 1, "lo")

    # Should be buffered, not yet written
    events = storage.read_events(task_dir)
    assert len(events) == 0

    await service.emit_llm_chunk(task_id, 1, " World")

    # Buffer reached size 3 → flushed
    events = storage.read_events(task_dir)
    assert len(events) == 3
    assert all(e["type"] == AgentEventType.LLM_CHUNK for e in events)


@pytest.mark.asyncio
async def test_non_chunk_event_flushes_buffer(storage_and_dir):
    """Non-chunk events should flush buffered chunks before writing."""
    storage, task_dir, task_id = storage_and_dir

    service = StreamEventService(file_storage=storage, chunk_flush_size=5)
    service.set_task_dir(task_id, task_dir)

    await service.emit_llm_chunk(task_id, 2, "A")
    await service.emit_llm_chunk(task_id, 2, "B")
    await service.emit(task_id, AgentEventType.TASK_CANCELLED, {})

    events = storage.read_events(task_dir)
    event_types = [e["type"] for e in events]
    assert event_types == [
        AgentEventType.LLM_CHUNK,
        AgentEventType.LLM_CHUNK,
        AgentEventType.TASK_CANCELLED,
    ]


@pytest.mark.asyncio
async def test_get_all_events_reads_from_file(storage_and_dir):
    """get_all_events should read from events.jsonl."""
    storage, task_dir, task_id = storage_and_dir

    service = StreamEventService(file_storage=storage)
    service.set_task_dir(task_id, task_dir)

    await service.emit(task_id, AgentEventType.TASK_STARTED, {})
    await service.emit_llm_chunk(task_id, 1, "hello")

    # Force flush of remaining chunks
    all_events_json = await service.get_all_events(task_id)
    all_events = [json.loads(e) for e in all_events_json]

    assert len(all_events) == 2
    assert all_events[0]["event_type"] == AgentEventType.TASK_STARTED
    assert all_events[1]["event_type"] == AgentEventType.LLM_CHUNK


@pytest.mark.asyncio
async def test_get_events_after_respects_last_event_id(storage_and_dir):
    """get_events_after should only return events after given seq."""
    storage, task_dir, task_id = storage_and_dir

    service = StreamEventService(file_storage=storage)
    service.set_task_dir(task_id, task_dir)

    await service.emit(task_id, "task:started", {})      # seq 1
    await service.emit(task_id, "llm:chunk", {})         # seq 2
    await service.emit(task_id, "llm:chunk", {})         # seq 3
    await service.emit(task_id, "task:completed", {})    # seq 4

    replayed = await service.get_events_after(task_id, "2")
    events = [json.loads(e) for e in replayed]

    assert len(events) == 2
    assert events[0]["id"] == "3"
    assert events[1]["id"] == "4"


@pytest.mark.asyncio
async def test_subscribe_and_push_to_queue(storage_and_dir):
    """Live subscribers should receive events via queue."""
    storage, task_dir, task_id = storage_and_dir

    service = StreamEventService(file_storage=storage)
    service.set_task_dir(task_id, task_dir)

    queue = await service.subscribe(task_id)

    await service.emit(task_id, AgentEventType.TASK_STARTED, {"key": "val"})

    event_json = await queue.get()
    event = json.loads(event_json)
    assert event["event_type"] == AgentEventType.TASK_STARTED
    assert event["data"]["key"] == "val"

    await service.unsubscribe(task_id, queue)


@pytest.mark.asyncio
async def test_emit_phase_changed(storage_and_dir):
    storage, task_dir, task_id = storage_and_dir

    service = StreamEventService(file_storage=storage)
    service.set_task_dir(task_id, task_dir)

    await service.emit_phase_changed(task_id, "planning", "idle", 2)

    events = storage.read_events(task_dir)
    assert len(events) == 1
    data = events[0]["data"]
    assert data["phase"] == "planning"
    assert data["previousPhase"] == "idle"
    assert data["turn"] == 2
