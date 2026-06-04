"""Task 聚合的领域事件。"""

from dataclasses import dataclass
from datetime import datetime

from src.domain.events.base import DomainEvent


@dataclass(frozen=True)
class TaskCreated(DomainEvent):
    """任务已创建"""

    task_id: str = ""
    agent_id: str = ""
    session_id: str = ""
    model: str = ""


@dataclass(frozen=True)
class TaskCompleted(DomainEvent):
    """任务已成功完成"""

    task_id: str = ""
    result: str = ""
    completed_at: datetime | None = None


@dataclass(frozen=True)
class TaskFailed(DomainEvent):
    """任务执行失败"""

    task_id: str = ""
    error: str = ""
    failed_at: datetime | None = None
