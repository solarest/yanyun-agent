"""Tests for TaskCompletionService with file-backed user message persistence."""

from datetime import datetime

import pytest

from src.application.services.session_file_storage import SessionFileStorage
from src.application.services.task_completion_service import TaskCompletionService
from src.domain.aggregates.session.session_message import (
    MessageStatus,
    SessionMessage,
    SessionMessageRole,
)
from src.domain.aggregates.task.task import Task, TaskConfig, TaskStatus


class FakeMessageRepo:
    """In-memory message repository for testing."""

    def __init__(self):
        self.messages: list[SessionMessage] = []

    async def add(self, message: SessionMessage) -> SessionMessage:
        self.messages.append(message)
        return message


class FakeTaskRepo:
    """In-memory task repository for testing."""

    def __init__(self):
        self.tasks: dict[str, Task] = {}

    async def update(self, task: Task) -> Task:
        self.tasks[task.id] = task
        return task


class FakeSessionRepo:
    """In-memory session repository for testing."""

    def __init__(self):
        self.sessions: dict = {}

    async def get_by_id(self, session_id: str):
        from src.domain.session.entity import Session
        return self.sessions.get(session_id)


def make_task(session_id: str = "sess-001") -> Task:
    return Task(
        message="Hello",
        workspace="/tmp/ws",
        status=TaskStatus.RUNNING,
        model="gpt-4",
        config=TaskConfig(max_turns=10),
        max_turns=10,
        agent_id="agent-1",
        session_id=session_id,
        started_at=datetime.now(),
    )


class TestFinalizeWithFileStorage:
    """Tests for finalize() with deferred user message persistence."""

    @pytest.mark.asyncio
    async def test_user_message_persisted_from_file(self, tmp_path):
        """finalize() should read user_msg.json and persist user message to DB."""
        storage = SessionFileStorage(base_path=str(tmp_path))
        task_dir = storage.create_task_dir("sess-001", "task-001")
        task = make_task(session_id="sess-001")
        task.id = "task-001"

        # Write user message to file (simulating SendMessageUseCase)
        user_msg_data = {
            "role": "user",
            "content": "Hello, agent!",
            "session_id": "sess-001",
            "task_id": "task-001",
        }
        storage.write_user_msg(task_dir, user_msg_data)

        message_repo = FakeMessageRepo()
        task_repo = FakeTaskRepo()

        service = TaskCompletionService(
            message_repo=message_repo,
            task_repo=task_repo,
            file_storage=storage,
        )
        result = {
            "final_result": "Hello, human!",
            "messages": [],
            "current_turn": 1,
        }

        await service.finalize(
            task=task,
            session_id="sess-001",
            result=result,
            task_dir=task_dir,
        )

        # Both user and assistant messages should be in the repo
        assert len(message_repo.messages) == 2
        roles = [m.role for m in message_repo.messages]
        assert SessionMessageRole.USER in roles
        assert SessionMessageRole.ASSISTANT in roles

        user_msg = [m for m in message_repo.messages if m.role == SessionMessageRole.USER][0]
        assert user_msg.content == "Hello, agent!"
        assert user_msg.session_id == "sess-001"

    @pytest.mark.asyncio
    async def test_skip_user_msg_when_no_file(self, tmp_path):
        """If user_msg.json doesn't exist, finalize should still persist assistant."""
        storage = SessionFileStorage(base_path=str(tmp_path))
        task_dir = storage.create_task_dir("sess-001", "task-001")
        task = make_task(session_id="sess-001")
        task.id = "task-001"

        # No user_msg.json written

        message_repo = FakeMessageRepo()
        task_repo = FakeTaskRepo()

        service = TaskCompletionService(
            message_repo=message_repo,
            task_repo=task_repo,
            file_storage=storage,
        )
        result = {
            "final_result": "Hello!",
            "messages": [],
            "current_turn": 1,
        }

        await service.finalize(
            task=task,
            session_id="sess-001",
            result=result,
            task_dir=task_dir,
        )

        # Only assistant message should be persisted
        assert len(message_repo.messages) == 1
        assert message_repo.messages[0].role == SessionMessageRole.ASSISTANT

    @pytest.mark.asyncio
    async def test_persist_session_messages_false_skips_all(self, tmp_path):
        """persist_session_messages=False should skip all message DB writes."""
        storage = SessionFileStorage(base_path=str(tmp_path))
        task_dir = storage.create_task_dir("sess-001", "task-001")
        task = make_task(session_id="sess-001")
        task.id = "task-001"

        storage.write_user_msg(task_dir, {"role": "user", "content": "Hi"})

        message_repo = FakeMessageRepo()
        task_repo = FakeTaskRepo()

        service = TaskCompletionService(
            message_repo=message_repo,
            task_repo=task_repo,
            file_storage=storage,
        )
        result = {"final_result": "Hi!", "messages": [], "current_turn": 1}

        await service.finalize(
            task=task,
            session_id="sess-001",
            result=result,
            task_dir=task_dir,
            persist_session_messages=False,
        )

        assert len(message_repo.messages) == 0

    @pytest.mark.asyncio
    async def test_user_message_has_task_id_set(self, tmp_path):
        """Persisted user message should have the task_id set."""
        storage = SessionFileStorage(base_path=str(tmp_path))
        task_dir = storage.create_task_dir("sess-001", "task-001")
        task = make_task(session_id="sess-001")
        task.id = "task-001"

        storage.write_user_msg(task_dir, {
            "role": "user",
            "content": "Ask something",
        })

        message_repo = FakeMessageRepo()
        service = TaskCompletionService(
            message_repo=message_repo,
            task_repo=FakeTaskRepo(),
            file_storage=storage,
        )
        result = {"final_result": "Answer", "messages": [], "current_turn": 1}

        await service.finalize(
            task=task,
            session_id="sess-001",
            result=result,
            task_dir=task_dir,
        )

        user_msg = [m for m in message_repo.messages if m.role == SessionMessageRole.USER][0]
        assert user_msg.task_id == "task-001"
