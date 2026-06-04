import asyncio

import pytest
from fastapi import FastAPI
from starlette.requests import Request

from src.application.dtos.event_dto import SSEEventDTO
from src.domain.entities.event_types import AgentEventType
from src.presentation.routes import sse_stream


class FakeEventService:
    def __init__(self, replay_events=None, live_events=None) -> None:
        self.replay_events = replay_events or []
        self.live_events = live_events or []
        self.after_event_id: str | None = None
        self.unsubscribed = False

    async def subscribe(self, _task_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        for event in self.live_events:
            await queue.put(event)
        return queue

    async def unsubscribe(self, _task_id: str, _queue: asyncio.Queue) -> None:
        self.unsubscribed = True

    async def get_all_events(self, _task_id: str):
        return list(self.replay_events)

    async def get_events_after(self, _task_id: str, last_event_id: str):
        self.after_event_id = last_event_id
        return list(self.replay_events)


def make_request(app: FastAPI, headers: dict[str, str] | None = None) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/tasks/task-1/stream",
        "headers": [
            (key.lower().encode("utf-8"), value.encode("utf-8"))
            for key, value in (headers or {}).items()
        ],
        "app": app,
        "query_string": b"",
        "scheme": "http",
        "client": ("testclient", 123),
        "server": ("testserver", 80),
        "http_version": "1.1",
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    request = Request(scope, receive)

    async def is_disconnected() -> bool:
        return False

    request.is_disconnected = is_disconnected  # type: ignore[method-assign]
    return request


@pytest.mark.asyncio
async def test_stream_route_replays_then_yields_live_events() -> None:
    replay_event = SSEEventDTO.create(
        "task-1", 2, AgentEventType.TASK_STARTED, {}).model_dump_json()
    live_event = SSEEventDTO.create(
        "task-1",
        3,
        AgentEventType.TASK_COMPLETED,
        {"result": "done"},
    ).model_dump_json()
    event_service = FakeEventService(
        replay_events=[replay_event], live_events=[live_event])
    app = FastAPI()
    app.state.event_service = event_service

    response = await sse_stream.stream_events(
        "task-1",
        make_request(app, headers={"last-event-id": "1"}),
    )

    chunk1 = await anext(response.body_iterator)
    chunk2 = await anext(response.body_iterator)
    await response.body_iterator.aclose()

    assert "event: task-started" in chunk1
    assert "event: task-completed" in chunk2
    assert event_service.after_event_id == "1"
    assert event_service.unsubscribed is True


@pytest.mark.asyncio
async def test_stream_route_emits_heartbeat_on_timeout(monkeypatch) -> None:
    event_service = FakeEventService()
    app = FastAPI()
    app.state.event_service = event_service

    async def fake_wait_for(_awaitable, timeout: float):
        _awaitable.close()
        raise asyncio.TimeoutError

    monkeypatch.setattr(sse_stream.asyncio, "wait_for", fake_wait_for)

    response = await sse_stream.stream_events("task-1", make_request(app))
    chunk = await anext(response.body_iterator)
    await response.body_iterator.aclose()

    assert chunk == ": heartbeat\n\n"
