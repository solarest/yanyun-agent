"""应用层 - Agent Loop 生命周期管理

封装 graph 执行后的 4 个异常处理分支。
原作 AgentLoopRunner.run() 中 try/except 块的逻辑。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from langgraph.errors import GraphInterrupt

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
    - handle_interrupt: 人在回路中断 → 注册 ResumeContext
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

    async def handle_interrupt(
        self,
        task: Task,
        session_id: str,
        graph: Any,
        config: dict,
        event_emitter: Optional[IEventEmitter],
        persist_session_messages: bool = True,
        task_dir: Optional[str] = None,
    ) -> None:
        """处理人在回路中断（GraphInterrupt）

        注册 ResumeContext，等待用户决策后恢复。
        """
        logger.info(
            "Agent loop interrupted for task %s — awaiting user confirmation", task.id
        )

        from src.infrastructure.agent.graph_resume_manager import (
            GraphResumeManager,
            ResumeContext,
            get_default_resume_manager,
        )

        resume_mgr = get_default_resume_manager()
        lifecycle = self  # capture for callback

        async def _on_resume_complete(result: dict) -> None:
            """图恢复执行完成后的回调。"""
            try:
                if lifecycle._task_repo:
                    task.status = TaskStatus.COMPLETED
                    task.completed_at = datetime.now()
                    await lifecycle._task_repo.update(task)
                await lifecycle._task_completion_service.finalize(
                    task=task,
                    session_id=session_id,
                    result=result,
                    event_emitter=event_emitter,
                    persist_session_messages=persist_session_messages,
                    task_dir=Path(task_dir) if task_dir else None,
                )
                # Clean up task_dir registration to prevent memory leak
                if hasattr(event_emitter, 'remove_task_dir'):
                    event_emitter.remove_task_dir(task.id)
                if event_emitter:
                    await event_emitter.emit(
                        task.id, AgentEventType.TASK_COMPLETED, {}
                    )
            except Exception:
                logger.exception(
                    "Resume completion callback failed for task %s", task.id
                )

        await resume_mgr.register(
            task.id,
            ResumeContext(
                graph=graph,
                config=config,
                task_id=task.id,
                session_id=session_id,
                on_complete=_on_resume_complete,
            ),
        )

        # 更新任务状态为"运行中"（非终态）
        if self._task_repo:
            task.status = TaskStatus.RUNNING
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
            task.status = TaskStatus.FAILED
            task.completed_at = datetime.now()
            task.error = str(error)
            await self._task_repo.update(task)
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
