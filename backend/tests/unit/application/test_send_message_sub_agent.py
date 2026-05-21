import pytest
from unittest.mock import AsyncMock

from langchain_core.messages import AIMessage, HumanMessage

from src.application.use_cases.send_message import SendMessageUseCase
from src.domain.entities.agent import Agent
from src.domain.entities.session_message import (
    MessageStatus,
    SessionMessage,
    SessionMessageRole,
)
from src.domain.entities.task import Task, TaskConfig, TaskStatus


class FakeAgentRepository:
    async def get_by_id(self, _agent_id: str) -> Agent:
        return Agent(name="Test Agent")


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
        self.list_calls = 0

    async def list_by_session(self, _session_id: str, limit: int = 20):
        self.list_calls += 1
        return [
            SessionMessage(
                session_id="session-1",
                role=SessionMessageRole.USER,
                content="parent user request",
                status=MessageStatus.COMPLETED,
            ),
            SessionMessage(
                session_id="session-1",
                role=SessionMessageRole.ASSISTANT,
                content="parent assistant context",
                status=MessageStatus.COMPLETED,
            ),
        ]

    async def add(self, message):
        self.saved_messages.append(message)
        return message


class FakeTaskRepository:
    def __init__(self) -> None:
        self.added_tasks = []
        self.updated_tasks = []

    async def add(self, task):
        self.added_tasks.append(task)
        return task

    async def update(self, task):
        self.updated_tasks.append(task)
        return task


class FakeEmitter:
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
            "phase:changed",
            {"phase": new_phase, "previousPhase": previous_phase, "turn": turn},
        )

    async def emit_llm_chunk(self, task_id: str, turn: int, text: str) -> None:
        await self.emit(task_id, "llm:chunk", {"turn": turn, "text": text})

    async def emit_thinking_chunk(self, task_id: str, turn: int, text: str) -> None:
        await self.emit(task_id, "thinking:chunk", {"turn": turn, "text": text})


class FakeToolRegistry:
    tool_count = 0

    def get_tool_defs(self, category=None):
        return []

    def list_tools(self):
        return []


class FakeSkillRepository:
    async def get_by_ids(self, _skill_ids):
        return []


class FakeLLMProvider:
    def create_chat_model(self, model=None, temperature=0.7, provider=None):
        return object()


class CapturingGraph:
    def __init__(self) -> None:
        self.initial_state = None

    async def ainvoke(self, initial_state, _config):
        self.initial_state = initial_state
        return {
            "messages": [AIMessage(content="child final answer")],
            "current_turn": 1,
            "phase": "complete",
            "final_result": None,
            "error": None,
        }


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


@pytest.mark.asyncio
async def test_sub_agent_runtime_uses_only_assigned_task_and_stores_final_answer(monkeypatch) -> None:
    message_repo = FakeMessageRepository()
    task_repo = FakeTaskRepository()
    graph = CapturingGraph()
    use_case = SendMessageUseCase(
        agent_repo=FakeAgentRepository(),
        session_repo=FakeSessionRepository(),
        message_repo=message_repo,
        task_repo=task_repo,
        event_emitter=FakeEmitter(),
        tool_registry=FakeToolRegistry(),
        skill_repo=FakeSkillRepository(),
        llm_provider=FakeLLMProvider(),
    )
    task = Task(
        id="sub-task-1",
        message="query one day weather",
        workspace="/tmp/workspace",
        status=TaskStatus.RUNNING,
        model="qwen3-max",
        config=TaskConfig(max_turns=50),
        max_turns=50,
        agent_id="agent-1",
        session_id="session-1",
    )

    monkeypatch.setattr(
        "src.application.use_cases.send_message.AgentWorkflowBuilder.build",
        lambda self: graph,
    )

    await use_case._run_agent_loop(
        agent_id="agent-1",
        session_id="session-1",
        task=task,
        content="query one day weather",
        model="qwen3-max",
        max_turns=50,
        workspace="/tmp/workspace",
        is_sub_agent=True,
        parent_task_id="parent-task-1",
        sub_agent_description="query one day weather",
        parent_system_prompt="parent system prompt",
        persist_session_messages=False,
    )

    assert message_repo.list_calls == 0
    assert graph.initial_state is not None
    assert len(graph.initial_state["messages"]) == 1
    only_message = graph.initial_state["messages"][0]
    assert isinstance(only_message, HumanMessage)
    assert only_message.content == "query one day weather"
    assert task_repo.updated_tasks[-1].result == "child final answer"
