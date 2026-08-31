"""应用层 - Agent Loop 生命周期管理

封装 graph 执行后的 4 个异常处理分支。
原作 AgentLoopRunner.run() 中 try/except 块的逻辑。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from src.domain.aggregates.task.task import TaskStatus
from src.domain.entities.event_types import AgentEventType

if TYPE_CHECKING:
    from src.domain.aggregates.task.task import Task
    from src.domain.repositories.task_repository import ITaskRepository
    from src.domain.services import IEventEmitter
    from src.application.services.task_completion_service import TaskCompletionService

logger = logging.getLogger(__name__)


class AgentLoopLifecycle:
    """Agent Loop 生命周期处理器

    封装 graph 执行完成后的 4 种处理分支：
    - handle_normal_completion: 正常完成 → finalize task
    - handle_awaiting_confirmation: 持久化确认等待态
    - handle_cancellation: 取消 → 更新 task 为 CANCELLED
    - handle_failure: 失败 → 更新 task 为 FAILED
    """

    def __init__(
        self,
        task_repo: Optional[ITaskRepository],
        task_completion_service: TaskCompletionService,
    ):
        self._task_repo = task_repo
        self._task_completion_service = task_completion_service

    async def handle_normal_completion(
        self,
        task: Task,
        session_id: str,
        result: dict,
        event_emitter: Optional[IEventEmitter],
        persist_session_messages: bool = True,
        task_dir: Optional[str] = None,
    ) -> None:
        """处理正常完成的 graph 执行"""
        from pathlib import Path

        await self._task_completion_service.finalize(
            task=task,
            session_id=session_id,
            result=result,
            event_emitter=event_emitter,
            persist_session_messages=persist_session_messages,
            task_dir=Path(task_dir) if task_dir else None,
        )

    async def handle_awaiting_confirmation(self, task: Task) -> None:
        """Keep a task resumable while its local snapshot awaits approval."""
        task.status = TaskStatus.RUNNING
        if self._task_repo:
            await self._task_repo.update(task)

    async def handle_cancellation(
        self,
        task: Task,
        event_emitter: Optional[IEventEmitter],
    ) -> None:
        """处理 agent loop 取消"""
        logger.info("Agent loop cancelled for task %s", task.id)
        if self._task_repo:
            task.status = TaskStatus.CANCELLED
            task.completed_at = datetime.now()
            task.error = "cancelled"
            await self._task_repo.update(task)
        if event_emitter:
            await event_emitter.emit_phase_changed(
                task.id,
                "cancelled",
                "thinking",
                task.current_turn,
            )
            await event_emitter.emit(
                task.id, AgentEventType.TASK_CANCELLED, {}
            )

    async def handle_failure(
        self,
        task: Task,
        error: Exception,
        event_emitter: Optional[IEventEmitter],
    ) -> None:
        """处理 agent loop 失败"""
        logger.exception("Agent loop failed for task %s: %s", task.id, error)
        if self._task_repo:
            try:
                task.status = TaskStatus.FAILED
                task.completed_at = datetime.now()
                task.error = str(error)
                await self._task_repo.update(task)
            except Exception:
                # DB 写入失败（如 session 处于 rollback 状态）不能吞掉终止事件，
                # 否则前端会一直停留在"思考中"且无法继续对话
                logger.exception(
                    "Failed to persist FAILED status for task %s", task.id
                )
        if event_emitter:
            await event_emitter.emit_phase_changed(
                task.id,
                "failed",
                "thinking",
                task.current_turn,
            )
            await event_emitter.emit(
                task.id, AgentEventType.TASK_FAILED, {"error": str(error)}
            )
