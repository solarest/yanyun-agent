import asyncio
from types import SimpleNamespace

import pytest

from src.application.use_cases.send_message import (
    SendMessageUseCase,
    _tool_defs_to_openai_functions,
)
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


class BlockingGraph:
    async def ainvoke(self, _state, _config):
        await asyncio.sleep(60)
        return {}


class ApprovalGraph:
    async def ainvoke(self, state, _config):
        return {
            **state,
            "current_turn": 1,
            "phase": "tool_executing",
            "awaiting_approval": True,
            "approval_request": {
                "toolCallId": "call-1",
                "toolName": "file_write",
                "input": {"path": "notes.txt", "content": "hello"},
                "riskLevel": "medium",
                "message": "Tool 'file_write' needs approval before it can run.",
            },
            "pending_tool_calls": [
                {"id": "call-1", "name": "file_write", "input": {"path": "notes.txt", "content": "hello"}}
            ],
        }


def test_tool_defs_to_openai_functions_keeps_approval_required_tools() -> None:
    class FakeToolRegistry:
        def list_tools(self):
            safe_tool = SimpleNamespace(
                policy=SimpleNamespace(requires_approval=False),
                to_tool_def=lambda: SimpleNamespace(
                    name="web_search",
                    description="search",
                    parameters=[],
                ),
            )
            gated_tool = SimpleNamespace(
                policy=SimpleNamespace(requires_approval=True),
                to_tool_def=lambda: SimpleNamespace(
                    name="file_write",
                    description="write",
                    parameters=[],
                ),
            )
            return [safe_tool, gated_tool]

    schemas = _tool_defs_to_openai_functions(FakeToolRegistry())

    assert [schema["function"]["name"] for schema in schemas] == [
        "web_search",
        "file_write",
    ]


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


@pytest.mark.asyncio
async def test_run_agent_loop_pauses_and_stores_pending_approval(monkeypatch) -> None:
    emitter = RecordingEmitter()
    task_repo = FakeTaskRepository()
    message_repo = FakeMessageRepository()
    approval_store = {}
    use_case = SendMessageUseCase(
        agent_repo=FakeAgentRepository(),
        session_repo=FakeSessionRepository(),
        message_repo=message_repo,
        task_repo=task_repo,
        event_emitter=emitter,
        tool_registry=FakeToolRegistry(),
        approval_store=approval_store,
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
        lambda self: ApprovalGraph(),
    )

    await use_case._run_agent_loop(
        agent_id="agent-1",
        session_id="session-1",
        task=task,
        content="hello",
        model=None,
        max_turns=3,
        workspace="/tmp",
    )

    assert task.status == TaskStatus.PAUSED
    assert task.id in approval_store
    assert [event["event_type"] for event in emitter.events] == [
        "task:started",
        "phase:changed",
        "session:message:saved",
        "approval:requested",
        "task:paused",
    ]
    assert "Approval required before running `file_write`." in message_repo.saved_messages[0].content


@pytest.mark.asyncio
async def test_resolve_pending_approval_approved_resumes_and_completes(monkeypatch) -> None:
    emitter = RecordingEmitter()
    task_repo = FakeTaskRepository()
    message_repo = FakeMessageRepository()
    running_tasks = {}
    approval_store = {}
    use_case = SendMessageUseCase(
        agent_repo=FakeAgentRepository(),
        session_repo=FakeSessionRepository(),
        message_repo=message_repo,
        task_repo=task_repo,
        event_emitter=emitter,
        tool_registry=FakeToolRegistry(),
        approval_store=approval_store,
        running_tasks=running_tasks,
    )
    task = Task(
        id="task-1",
        message="hello",
        workspace="/tmp",
        status=TaskStatus.PAUSED,
        config=TaskConfig(max_turns=3),
        max_turns=3,
        current_turn=1,
        agent_id="agent-1",
        session_id="session-1",
    )
    approval_store[task.id] = SimpleNamespace(
        use_case=use_case,
        task=task,
        agent_id="agent-1",
        session_id="session-1",
        model=None,
        max_turns=3,
        workspace="/tmp",
        state={
            "messages": [],
            "task_id": task.id,
            "workspace": "/tmp",
            "user_message": "hello",
            "task_start_message_count": 0,
            "current_turn": 1,
            "max_turns": 3,
            "phase": "paused",
            "should_end": False,
            "is_complete": False,
            "pending_tool_calls": [{"id": "call-1", "name": "file_write", "input": {"path": "notes.txt"}}],
            "tool_results": {},
            "awaiting_user_input": False,
            "awaiting_approval": True,
            "approval_request": {
                "toolCallId": "call-1",
                "toolName": "file_write",
                "input": {"path": "notes.txt"},
                "riskLevel": "medium",
                "message": "Tool 'file_write' needs approval before it can run.",
            },
            "approved_tool_call_ids": [],
            "last_executed_tool_call_ids": [],
            "loop_detection_count": 0,
            "loop_detected": False,
            "loop_type": None,
            "stuck_detection_count": 0,
            "stuck_detected": False,
            "stuck_type": None,
            "current_llm_text": "",
            "empty_retry_count": 0,
            "planning_retry_count": 0,
            "system_prompt": "",
            "final_result": None,
            "error": None,
        },
        approval_request={
            "toolCallId": "call-1",
            "toolName": "file_write",
            "input": {"path": "notes.txt"},
            "riskLevel": "medium",
            "message": "Tool 'file_write' needs approval before it can run.",
        },
    )

    monkeypatch.setattr(
        "src.application.use_cases.send_message.create_chat_model",
        lambda model=None: object(),
    )

    async def fake_tool_execute_node(state, config):
        return {
            "messages": [],
            "tool_results": {
                "call-1": {
                    "tool_name": "file_write",
                    "status": "success",
                    "output": "done",
                    "error": None,
                    "metadata": {},
                }
            },
            "pending_tool_calls": [],
            "awaiting_user_input": False,
            "awaiting_approval": False,
            "approval_request": None,
            "approved_tool_call_ids": state["approved_tool_call_ids"],
            "last_executed_tool_call_ids": ["call-1"],
            "final_result": None,
            "phase": "tool_executing",
        }

    class CompletionGraph:
        async def ainvoke(self, state, _config):
            return {**state, "final_result": "completed", "error": None, "phase": "thinking"}

    monkeypatch.setattr("src.application.use_cases.send_message.tool_execute_node", fake_tool_execute_node)
    monkeypatch.setattr(
        "src.application.use_cases.send_message.AgentWorkflowBuilder.build",
        lambda self: CompletionGraph(),
    )

    asyncio_task = await use_case.resolve_pending_approval(task.id, True)
    await asyncio_task

    event_types = [event["event_type"] for event in emitter.events]
    assert "approval:resolved" in event_types
    assert "task:resumed" in event_types
    assert "task:completed" in event_types
    assert task.status == TaskStatus.COMPLETED


@pytest.mark.asyncio
async def test_sub_agent_approval_resumes_child_and_returns_to_plan(monkeypatch) -> None:
    emitter = RecordingEmitter()
    task_repo = FakeTaskRepository()
    message_repo = FakeMessageRepository()
    approval_store = {}
    use_case = SendMessageUseCase(
        agent_repo=FakeAgentRepository(),
        session_repo=FakeSessionRepository(),
        message_repo=message_repo,
        task_repo=task_repo,
        event_emitter=emitter,
        tool_registry=FakeToolRegistry(),
        approval_store=approval_store,
    )
    parent_task = Task(
        id="task-1",
        message="hello",
        workspace="/tmp",
        status=TaskStatus.RUNNING,
        config=TaskConfig(max_turns=3),
        max_turns=3,
        current_turn=1,
        agent_id="agent-1",
        session_id="session-1",
    )
    task_repo.tasks[parent_task.id] = parent_task

    resume_future = asyncio.get_running_loop().create_future()
    sub_state = {
        "messages": [],
        "task_id": "sub-task-1",
        "workspace": "/tmp",
        "user_message": "write",
        "task_start_message_count": 0,
        "current_turn": 1,
        "max_turns": 3,
        "phase": "tool_executing",
        "should_end": False,
        "is_complete": False,
        "pending_tool_calls": [
            {"id": "call-1", "name": "file_write", "input": {"path": "notes.txt"}}
        ],
        "tool_results": {},
        "awaiting_user_input": False,
        "awaiting_approval": True,
        "approval_request": {
            "toolCallId": "call-1",
            "toolName": "file_write",
            "input": {"path": "notes.txt"},
            "riskLevel": "medium",
            "message": "Tool 'file_write' needs approval before it can run.",
        },
        "approved_tool_call_ids": [],
        "last_executed_tool_call_ids": [],
        "loop_detection_count": 0,
        "loop_detected": False,
        "loop_type": None,
        "stuck_detection_count": 0,
        "stuck_detected": False,
        "stuck_type": None,
        "current_llm_text": "",
        "empty_retry_count": 0,
        "planning_retry_count": 0,
        "system_prompt": "",
        "final_result": None,
        "error": None,
    }

    await use_case._pause_sub_agent_for_approval(
        parent_task=parent_task,
        agent_id="agent-1",
        model=None,
        workspace="/tmp",
        result=sub_state,
        sub_tool_registry=FakeToolRegistry(),
        step_id=2,
        resume_future=resume_future,
    )

    monkeypatch.setattr(
        "src.application.use_cases.send_message.create_chat_model",
        lambda model=None: object(),
    )

    async def fake_tool_execute_node(state, config):
        return {
            "messages": [],
            "tool_results": {
                "call-1": {
                    "tool_name": "file_write",
                    "status": "success",
                    "output": "written",
                    "error": None,
                    "metadata": {},
                }
            },
            "pending_tool_calls": [],
            "awaiting_user_input": False,
            "awaiting_approval": False,
            "approval_request": None,
            "approved_tool_call_ids": state["approved_tool_call_ids"],
            "last_executed_tool_call_ids": ["call-1"],
            "final_result": None,
            "phase": "tool_executing",
        }

    class CompletionGraph:
        async def ainvoke(self, state, _config):
            return {
                **state,
                "final_result": "sub step completed",
                "error": None,
                "phase": "thinking",
            }

    monkeypatch.setattr("src.application.use_cases.send_message.tool_execute_node", fake_tool_execute_node)
    monkeypatch.setattr(
        "src.application.use_cases.send_message.AgentWorkflowBuilder.build",
        lambda self: CompletionGraph(),
    )

    resume_task = await use_case.resolve_pending_approval(parent_task.id, True)
    await resume_task

    assert resume_future.result() == {
        "task_id": "sub-task-1",
        "final_result": "sub step completed",
        "error": None,
    }
    assert parent_task.status == TaskStatus.RUNNING
    event_types = [event["event_type"] for event in emitter.events]
    assert "approval:requested" in event_types
    assert "approval:resolved" in event_types
    assert "task:resumed" in event_types
