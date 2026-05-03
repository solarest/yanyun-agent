import asyncio

import pytest

from src.application.use_cases.send_message import SendMessageUseCase
from src.domain.entities.agent import Agent
from src.domain.entities.task import Task, TaskConfig, TaskStatus


class RecordingEmitter:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def emit(self, task_id: str, event_type: str, payload: dict) -> None:
        self.events.append(
            {"task_id": task_id, "event_type": event_type, "payload": payload}
        )

    async def emit_phase_changed(
        self,
        task_id: str,
        new_phase: str,
        previous_phase: str,
        turn: int,
    ) -> None:
        await self.emit(
            task_id,
            "phase:changed",
            {
                "phase": new_phase,
                "previousPhase": previous_phase,
                "turn": turn,
            },
        )

    async def emit_llm_chunk(self, task_id: str, turn: int, text: str) -> None:
        await self.emit(
            task_id,
            "llm:chunk",
            {"turn": turn, "text": text, "delta": True},
        )


class FakeAgentRepository:
    async def get_by_id(self, _agent_id: str) -> Agent:
        return Agent(name="Test Agent")


class FakeSessionRepository:
    async def get_by_id(self, _session_id: str):
        return None

    async def update(self, session):
        return session


class FakeMessageRepository:
    def __init__(self) -> None:
        self.saved_messages = []

    async def list_by_session(self, _session_id: str, limit: int = 20):
        return []

    async def add(self, message):
        self.saved_messages.append(message)
        return message


class FakeTaskRepository:
    def __init__(self) -> None:
        self.updated: Task | None = None
        self.tasks: dict[str, Task] = {}

    async def get_by_id(self, task_id: str) -> Task | None:
        return self.tasks.get(task_id)

    async def update(self, task: Task) -> Task:
        self.updated = task
        self.tasks[task.id] = task
        return task


class FakeToolRegistry:
    tool_count = 0

    def register(self, tool):
        pass

    def get_tool_defs(self, category=None):
        return []


class BlockingGraph:
    async def ainvoke(self, _state, _config):
        await asyncio.sleep(60)
        return {}


@pytest.mark.asyncio
async def test_run_agent_loop_emits_cancelled_terminal_event(monkeypatch) -> None:
    emitter = RecordingEmitter()
    task_repo = FakeTaskRepository()
    use_case = SendMessageUseCase(
        agent_repo=FakeAgentRepository(),
        session_repo=FakeSessionRepository(),
        message_repo=FakeMessageRepository(),
        task_repo=task_repo,
        event_emitter=emitter,
        tool_registry=FakeToolRegistry(),
    )
    task = Task(
        message="hello",
        workspace="/tmp",
        status=TaskStatus.RUNNING,
        config=TaskConfig(max_turns=3),
        max_turns=3,
        agent_id="agent-1",
        session_id="session-1",
    )

    monkeypatch.setattr(
        "src.application.use_cases.send_message.create_chat_model",
        lambda model=None: object(),
    )
    monkeypatch.setattr(
        "src.application.use_cases.send_message.AgentWorkflowBuilder.build",
        lambda self: BlockingGraph(),
    )

    runner = asyncio.create_task(
        use_case._run_agent_loop(
            agent_id="agent-1",
            session_id="session-1",
            task=task,
            content="hello",
            model=None,
            max_turns=3,
            workspace="/tmp",
        )
    )

    await asyncio.sleep(0.05)
    runner.cancel()
    await runner

    event_types = [event["event_type"] for event in emitter.events]
    assert "task:cancelled" in event_types
    assert "task:failed" not in event_types
    assert task.status == TaskStatus.CANCELLED
    assert task_repo.updated is task
