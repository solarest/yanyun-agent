from types import SimpleNamespace

import pytest

from src.application.tasks.management import TaskManagementUseCase
from src.domain.aggregates.task.task import TaskStatus
from src.domain.entities.event_types import AgentEventType
from src.infrastructure.tools.confirmation.store import PendingApprovalRegistry


class FakeTaskRepository:
    def __init__(self, task) -> None:
        self.task = task
        self.updated = []

    async def get_by_id(self, task_id: str):
        return self.task if task_id == self.task.id else None

    async def update(self, task):
        self.updated.append(task)
        return task


class RecordingEmitter:
    def __init__(self) -> None:
        self.events = []

    async def emit_phase_changed(self, task_id, phase, previous_phase, turn) -> None:
        self.events.append(("phase", task_id, phase, previous_phase, turn))

    async def emit(self, task_id, event_type, payload) -> None:
        self.events.append(("event", task_id, event_type, payload))


@pytest.mark.asyncio
async def test_cancel_waiting_confirmation_marks_task_terminal_and_cleans_approval_state() -> None:
    task = SimpleNamespace(
        id="task-awaiting-confirmation",
        status=TaskStatus.RUNNING,
        current_turn=2,
        completed_at=None,
        error=None,
    )
    task_repo = FakeTaskRepository(task)
    emitter = RecordingEmitter()
    approval_registry = PendingApprovalRegistry()
    await approval_registry.register(task.id, "call-dangerous")
    use_case = TaskManagementUseCase(
        task_repo=task_repo,
        agent_repo=object(),
        running_tasks={},
        event_emitter=emitter,
        approval_registry=approval_registry,
    )

    result = await use_case.cancel(task.id)

    assert result == {"task_id": task.id, "cancelled": True}
    assert task.status == TaskStatus.CANCELLED
    assert task.error == "cancelled"
    assert task.completed_at is not None
    assert task_repo.updated == [task]
    assert not await approval_registry.has(task.id, "call-dangerous")
    assert ("event", task.id, AgentEventType.TASK_CANCELLED, {}) in emitter.events
