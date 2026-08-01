"""Tests for AgentLoopLifecycle

Covers 4 lifecycle branches:
- handle_normal_completion → finalize task
- handle_interrupt → register ResumeContext
- handle_cancellation → set CANCELLED + emit events
- handle_failure → set FAILED + emit events
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langgraph.errors import GraphInterrupt

from src.application.services.agent_loop_lifecycle import AgentLoopLifecycle
from src.domain.aggregates.task.task import TaskStatus
from src.domain.entities.event_types import AgentEventType


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

@pytest.fixture
def task():
    """Create a minimal Task."""
    t = MagicMock()
    t.id = "task-1"
    t.status = TaskStatus.RUNNING
    t.current_turn = 3
    t.completed_at = None
    t.error = None
    return t


@pytest.fixture
def task_repo():
    """Mock ITaskRepository."""
    repo = MagicMock()
    repo.update = AsyncMock()
    return repo


@pytest.fixture
def completion_service():
    """Mock TaskCompletionService."""
    svc = MagicMock()
    svc.finalize = AsyncMock()
    return svc


@pytest.fixture
def event_emitter():
    """Mock IEventEmitter."""
    em = MagicMock()
    em.emit = AsyncMock()
    em.emit_phase_changed = AsyncMock()
    return em


@pytest.fixture
def lifecycle(task_repo, completion_service):
    return AgentLoopLifecycle(
        task_repo=task_repo,
        task_completion_service=completion_service,
    )


# ─────────────────────────────────────────────────────────────────
# Normal Completion
# ─────────────────────────────────────────────────────────────────

class TestNormalCompletion:

    @pytest.mark.asyncio
    async def test_delegates_to_task_completion_service(self, lifecycle, task, event_emitter, completion_service):
        """handle_normal_completion() calls TaskCompletionService.finalize()"""
        result = {"messages": [], "phase": "complete"}

        await lifecycle.handle_normal_completion(
            task=task,
            session_id="sess-1",
            result=result,
            event_emitter=event_emitter,
            persist_session_messages=True,
        )

        completion_service.finalize.assert_called_once()
        call_kwargs = completion_service.finalize.call_args[1]
        assert call_kwargs["task"] == task
        assert call_kwargs["session_id"] == "sess-1"
        assert call_kwargs["event_emitter"] == event_emitter


# ─────────────────────────────────────────────────────────────────
# Interrupt (Human-in-the-loop)
# ─────────────────────────────────────────────────────────────────

class TestInterrupt:

    @pytest.mark.asyncio
    async def test_registers_resume_context(self, lifecycle, task, event_emitter):
        """handle_interrupt() registers a ResumeContext for graph resumption"""
        graph = MagicMock()
        config = {"configurable": {"thread_id": "task-1"}}

        with patch(
            "src.infrastructure.agent.graph_resume_manager.get_default_resume_manager"
        ) as mock_get_mgr:
            mock_mgr = MagicMock()
            mock_mgr.register = AsyncMock()
            mock_get_mgr.return_value = mock_mgr

            await lifecycle.handle_interrupt(
                task=task,
                session_id="sess-1",
                graph=graph,
                config=config,
                event_emitter=event_emitter,
            )

            mock_mgr.register.assert_called_once()
            resume_ctx = mock_mgr.register.call_args[0][1]
            assert resume_ctx.graph == graph
            assert resume_ctx.config == config
            assert resume_ctx.task_id == "task-1"
            assert resume_ctx.session_id == "sess-1"

    @pytest.mark.asyncio
    async def test_updates_task_status_to_running(self, lifecycle, task, task_repo, event_emitter):
        """handle_interrupt() keeps task status as RUNNING (not terminal)"""
        with patch(
            "src.infrastructure.agent.graph_resume_manager.get_default_resume_manager"
        ) as mock_get_mgr:
            mock_mgr = MagicMock()
            mock_mgr.register = AsyncMock()
            mock_get_mgr.return_value = mock_mgr

            await lifecycle.handle_interrupt(
                task=task,
                session_id="sess-1",
                graph=MagicMock(),
                config={},
                event_emitter=event_emitter,
            )

            assert task.status == TaskStatus.RUNNING
            task_repo.update.assert_called_with(task)


# ─────────────────────────────────────────────────────────────────
# Cancellation
# ─────────────────────────────────────────────────────────────────

class TestCancellation:

    @pytest.mark.asyncio
    async def test_sets_task_cancelled(self, lifecycle, task, task_repo, event_emitter):
        """handle_cancellation() sets status CANCELLED + error='cancelled'"""
        await lifecycle.handle_cancellation(
            task=task,
            event_emitter=event_emitter,
        )

        assert task.status == TaskStatus.CANCELLED
        assert task.error == "cancelled"
        assert task.completed_at is not None
        task_repo.update.assert_called_with(task)

    @pytest.mark.asyncio
    async def test_emits_cancelled_events(self, lifecycle, task, event_emitter):
        """handle_cancellation() emits phase_changed + TASK_CANCELLED event"""
        await lifecycle.handle_cancellation(
            task=task,
            event_emitter=event_emitter,
        )

        event_emitter.emit_phase_changed.assert_called_once()
        event_emitter.emit.assert_called_with(
            task.id, AgentEventType.TASK_CANCELLED, {}
        )

    @pytest.mark.asyncio
    async def test_handles_null_task_repo(self, completion_service, task, event_emitter):
        """handle_cancellation() is safe when task_repo is None"""
        lifecycle = AgentLoopLifecycle(
            task_repo=None,
            task_completion_service=completion_service,
        )
        await lifecycle.handle_cancellation(
            task=task,
            event_emitter=event_emitter,
        )
        # Should not raise — task.status not modified
        event_emitter.emit.assert_called_with(
            task.id, AgentEventType.TASK_CANCELLED, {}
        )

    @pytest.mark.asyncio
    async def test_handles_null_event_emitter(self, lifecycle, task, task_repo):
        """handle_cancellation() is safe when event_emitter is None"""
        await lifecycle.handle_cancellation(
            task=task,
            event_emitter=None,
        )
        assert task.status == TaskStatus.CANCELLED
        task_repo.update.assert_called_with(task)


# ─────────────────────────────────────────────────────────────────
# Failure
# ─────────────────────────────────────────────────────────────────

class TestFailure:

    @pytest.mark.asyncio
    async def test_sets_task_failed(self, lifecycle, task, task_repo, event_emitter):
        """handle_failure() sets status FAILED + error message"""
        error = RuntimeError("LLM timeout")

        await lifecycle.handle_failure(
            task=task,
            error=error,
            event_emitter=event_emitter,
        )

        assert task.status == TaskStatus.FAILED
        assert task.error == "LLM timeout"
        assert task.completed_at is not None
        task_repo.update.assert_called_with(task)

    @pytest.mark.asyncio
    async def test_emits_failed_events(self, lifecycle, task, event_emitter):
        """handle_failure() emits phase_changed + TASK_FAILED with error"""
        error = RuntimeError("bad thing")

        await lifecycle.handle_failure(
            task=task,
            error=error,
            event_emitter=event_emitter,
        )

        event_emitter.emit_phase_changed.assert_called_once()
        event_emitter.emit.assert_called_with(
            task.id,
            AgentEventType.TASK_FAILED,
            {"error": "bad thing"},
        )

    @pytest.mark.asyncio
    async def test_handles_null_task_repo(self, completion_service, task, event_emitter):
        """handle_failure() is safe when task_repo is None"""
        lifecycle = AgentLoopLifecycle(
            task_repo=None,
            task_completion_service=completion_service,
        )

        await lifecycle.handle_failure(
            task=task,
            error=RuntimeError("test"),
            event_emitter=event_emitter,
        )
        event_emitter.emit.assert_called_with(
            task.id,
            AgentEventType.TASK_FAILED,
            {"error": "test"},
        )
