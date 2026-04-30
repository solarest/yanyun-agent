import json
from collections import defaultdict
from contextlib import asynccontextmanager

import pytest

from src.application.dtos.event_dto import SSEEventDTO
from src.application.use_cases.stream_event import StreamEventService


class InMemoryEventRepository:
    def __init__(self) -> None:
        self.events: dict[str, list[SSEEventDTO]] = defaultdict(list)
        self.single_saves = 0
        self.batch_saves = 0

    async def save(self, task_id: str, event: SSEEventDTO) -> None:
        self.single_saves += 1
        self.events[task_id].append(event)

    async def save_batch(self, task_id: str, events: list[SSEEventDTO]) -> None:
        self.batch_saves += 1
        self.events[task_id].extend(events)

    async def get_after(self, task_id: str, last_event_id: str) -> list[SSEEventDTO]:
        last_seq = int(last_event_id)
        return [event for event in self.events[task_id] if int(event.id) > last_seq]

    async def get_by_task_id(self, task_id: str) -> list[SSEEventDTO]:
        return list(self.events[task_id])


def make_event_repo_factory(repo: InMemoryEventRepository):
    @asynccontextmanager
    async def _factory():
        yield repo

    return _factory


@pytest.mark.asyncio
async def test_stream_event_service_normalizes_events_and_flushes_on_replay() -> None:
    repo = InMemoryEventRepository()
    service = StreamEventService(make_event_repo_factory(repo), chunk_flush_size=5)

    await service.emit("task-1", "task-started", {})
    await service.emit_llm_chunk("task-1", 1, "Hel")
    await service.emit_llm_chunk("task-1", 1, "lo")

    assert repo.single_saves == 1
    assert repo.batch_saves == 0

    all_events = [json.loads(item) for item in await service.get_all_events("task-1")]
    assert [event["event_type"] for event in all_events] == [
        "task:started",
        "llm:chunk",
        "llm:chunk",
    ]
    assert repo.batch_saves == 1

    replayed = [json.loads(item) for item in await service.get_events_after("task-1", "1")]
    assert [event["id"] for event in replayed] == ["2", "3"]


@pytest.mark.asyncio
async def test_non_chunk_event_flushes_chunk_buffer_before_cancelled_terminal_event() -> None:
    repo = InMemoryEventRepository()
    service = StreamEventService(make_event_repo_factory(repo), chunk_flush_size=10)

    await service.emit_llm_chunk("task-2", 2, "A")
    await service.emit_llm_chunk("task-2", 2, "B")
    await service.emit("task-2", "task:cancelled", {})

    stored = repo.events["task-2"]
    assert [event.event_type for event in stored] == [
        "llm:chunk",
        "llm:chunk",
        "task:cancelled",
    ]
    assert repo.batch_saves == 1
    assert repo.single_saves == 1
