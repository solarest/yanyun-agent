import pytest
from unittest.mock import AsyncMock

from src.application.use_cases.send_message import SendMessageUseCase
from src.domain.entities.task import Task, TaskConfig, TaskStatus


class FakeAgentRepository:
    pass


class FakeSessionRepository:
    def __init__(self) -> None:
        self.get_calls = 0
        self.update_calls = 0

    async def get_by_id(self, _session_id: str):
        self.get_calls += 1
        return None

    async def update(self, session):
        self.update_calls += 1
        return session


class FakeMessageRepository:
    def __init__(self) -> None:
        self.saved_messages = []

    async def add(self, message):
        self.saved_messages.append(message)
        return message


class FakeTaskRepository:
    def __init__(self) -> None:
        self.added_tasks = []

    async def add(self, task):
        self.added_tasks.append(task)
        return task


class FakeEmitter:
    pass


class FakeToolRegistry:
    tool_count = 0

    def get_tool_defs(self, category=None):
        return []


@pytest.mark.asyncio
async def test_sub_agent_execute_reuses_task_and_passes_runtime_state() -> None:
    session_repo = FakeSessionRepository()
    message_repo = FakeMessageRepository()
    task_repo = FakeTaskRepository()
    use_case = SendMessageUseCase(
        agent_repo=FakeAgentRepository(),
        session_repo=session_repo,
        message_repo=message_repo,
        task_repo=task_repo,
        event_emitter=FakeEmitter(),
        tool_registry=FakeToolRegistry(),
    )
    use_case._run_agent_loop = AsyncMock()  # type: ignore[method-assign]

    sub_task = Task(
        id="sub-task-1",
        message="inspect files",
        workspace="/tmp/workspace",
        status=TaskStatus.RUNNING,
        model="gpt-4o",
        config=TaskConfig(max_turns=50),
        max_turns=50,
        agent_id="agent-1",
        session_id="session-1",
    )

    result = await use_case.execute(
        agent_id="agent-1",
        session_id="session-1",
        content="inspect files",
        model="gpt-4o",
        max_turns=50,
        workspace="/tmp/workspace",
        is_sub_agent=True,
        parent_task_id="parent-task-1",
        sub_agent_description="inspect files",
        parent_system_prompt="parent prompt",
        sub_task=sub_task,
        allowed_tools=["file_read"],
    )
    await result["asyncio_task"]

    assert result["task_id"] == "sub-task-1"
    assert result["user_message"] is None
    assert task_repo.added_tasks == []
    assert message_repo.saved_messages == []
    assert session_repo.get_calls == 0

    run_kwargs = use_case._run_agent_loop.call_args.kwargs  # type: ignore[attr-defined]
    assert run_kwargs["task"] is sub_task
    assert run_kwargs["is_sub_agent"] is True
    assert run_kwargs["parent_task_id"] == "parent-task-1"
    assert run_kwargs["sub_agent_description"] == "inspect files"
    assert run_kwargs["parent_system_prompt"] == "parent prompt"
    assert run_kwargs["allowed_tools"] == ["file_read"]
    assert run_kwargs["persist_session_messages"] is False


@pytest.mark.asyncio
async def test_execute_passes_effective_default_model_into_runtime_state(monkeypatch) -> None:
    monkeypatch.setenv("LLM_DEFAULT_MODEL", "qwen3-max")
    monkeypatch.setenv("LLM_DEFAULT_PROVIDER", "qwen")

    use_case = SendMessageUseCase(
        agent_repo=FakeAgentRepository(),
        session_repo=FakeSessionRepository(),
        message_repo=FakeMessageRepository(),
        task_repo=FakeTaskRepository(),
        event_emitter=FakeEmitter(),
        tool_registry=FakeToolRegistry(),
    )
    use_case._run_agent_loop = AsyncMock()  # type: ignore[method-assign]

    result = await use_case.execute(
        agent_id="agent-1",
        session_id="session-1",
        content="hello",
        model=None,
        workspace="/tmp/workspace",
    )
    await result["asyncio_task"]

    run_kwargs = use_case._run_agent_loop.call_args.kwargs  # type: ignore[attr-defined]
    assert run_kwargs["model"] == "qwen3-max"
    assert run_kwargs["task"].model == "qwen3-max"
