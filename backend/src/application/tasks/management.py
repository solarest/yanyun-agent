"""应用层 - Task 管理用例

编排 Task 的创建与取消操作。
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from src.domain.entities.event_types import AgentEventType
from src.domain.repositories.agent_repository import IAgentRepository
from src.domain.repositories.task_repository import ITaskRepository
from src.domain.services import IEventEmitter
from src.domain.task.entity import Task, TaskConfig, TaskStatus

logger = logging.getLogger(__name__)


class TaskManagementUseCase:
    """Task 管理用例

    职责：
    - 创建 Task（含 Agent 存在校验）
    - 取消 Task（含状态校验、asyncio 取消、事件发射）
    """

    def __init__(
        self,
        task_repo: ITaskRepository,
        agent_repo: IAgentRepository,
        running_tasks: Optional[Dict[str, asyncio.Task]] = None,
        event_emitter: Optional[IEventEmitter] = None,
        resume_manager: Any = None,
        approval_registry: Any = None,
    ) -> None:
        self._task_repo = task_repo
        self._agent_repo = agent_repo
        self._running_tasks = running_tasks if running_tasks is not None else {}
        self._event_emitter = event_emitter
        self._resume_manager = resume_manager
        self._approval_registry = approval_registry

    async def create(
        self,
        message: str,
        workspace: str = "/tmp/agent-workspace",
        agent_id: Optional[str] = None,
        model: Optional[str] = "gpt-4",
        max_turns: int = 100,
    ) -> Task:
        """创建任务

        如果指定了 agent_id，会校验 Agent 是否存在。
        任务创建后处于 idle 状态，等待执行。

        Args:
            message: 任务消息描述
            workspace: 工作目录
            agent_id: 关联的 Agent ID（可选）
            model: 模型名称
            max_turns: 最大执行轮次

        Returns:
            创建的 Task 实体

        Raises:
            AgentNotFoundError: 关联的 Agent 不存在
        """
        if agent_id is not None:
            agent = await self._agent_repo.get_by_id(agent_id)
            if agent is None:
                raise AgentNotFoundError(agent_id)

        task = Task(
            message=message,
            workspace=workspace,
            status=TaskStatus.IDLE,
            model=model or "gpt-4",
            config=TaskConfig(max_turns=max_turns),
            agent_id=agent_id,
        )

        return await self._task_repo.add(task)

    async def cancel(self, task_id: str) -> Dict[str, Any]:
        """取消运行中的任务

        从 running_tasks 中取出 asyncio.Task 并取消。
        如果任务已暂停且没有对应的 asyncio.Task，则直接标记为 CANCELLED
        并发射相关事件。

        Args:
            task_id: 任务 ID

        Returns:
            {"task_id": str, "cancelled": bool}

        Raises:
            TaskNotFoundError: 任务不存在
            TaskNotRunningError: 任务不在可取消状态
        """
        task = await self._task_repo.get_by_id(task_id)
        if task is None:
            raise TaskNotFoundError(task_id)

        if task.status not in (TaskStatus.RUNNING, TaskStatus.PAUSED):
            raise TaskNotRunningError(task_id)

        asyncio_task = self._running_tasks.get(task_id)
        if asyncio_task is not None:
            asyncio_task.cancel()
            return {"task_id": task_id, "cancelled": True}

        # 确认等待态也会保持 RUNNING，但对应的图执行任务已经结束。
        # 此时必须自行完成取消，而不能只返回成功。
        if task.status in (TaskStatus.RUNNING, TaskStatus.PAUSED):
            task.status = TaskStatus.CANCELLED
            task.completed_at = datetime.now()
            task.error = "cancelled"
            await self._task_repo.update(task)

            if self._resume_manager:
                await self._resume_manager.remove(task_id)
            if self._approval_registry:
                await self._approval_registry.remove_task(task_id)

            if self._event_emitter:
                await self._event_emitter.emit_phase_changed(
                    task_id,
                    "cancelled",
                    "awaiting_confirmation",
                    task.current_turn,
                )
                await self._event_emitter.emit(
                    task_id, AgentEventType.TASK_CANCELLED, {}
                )

        return {"task_id": task_id, "cancelled": True}


# ── 业务异常 ──────────────────────────────────────────────


class TaskNotFoundError(Exception):
    """任务不存在"""

    def __init__(self, task_id: str) -> None:
        self.task_id = task_id
        super().__init__(f"Task '{task_id}' not found")


class AgentNotFoundError(Exception):
    """Agent 不存在（创建任务时）"""

    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        super().__init__(f"Agent '{agent_id}' not found")


class TaskNotRunningError(Exception):
    """任务不在可取消状态"""

    def __init__(self, task_id: str) -> None:
        self.task_id = task_id
        super().__init__(f"Task '{task_id}' is not in a cancellable state")
