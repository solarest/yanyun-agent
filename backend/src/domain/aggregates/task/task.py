"""领域层 - Task 聚合根"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from src.domain.aggregates.task.cost_tracker import CostTracker
from src.domain.entities.base import Entity


class TaskStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


@dataclass
class TaskConfig:
    max_turns: int = 100
    model: str = "gpt-4"
    temperature: float = 0.7


@dataclass
class Task(Entity):
    """Agent 任务聚合根"""

    message: str = ""
    workspace: str = ""
    status: TaskStatus = TaskStatus.IDLE
    model: str = ""
    config: TaskConfig = field(default_factory=TaskConfig)
    current_turn: int = 0
    max_turns: int = 100
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[str] = None
    error: Optional[str] = None
    cost: CostTracker = field(default_factory=CostTracker)
    agent_id: Optional[str] = None
    session_id: Optional[str] = None

    # === 工厂方法 ===

    @classmethod
    def create(
        cls,
        message: str,
        *,
        agent_id: str,
        session_id: str,
        model: str,
        workspace: str = "/tmp/agent-workspace",
        max_turns: int = 100,
    ) -> "Task":
        """创建新任务（工厂方法）"""
        return cls(
            message=message,
            workspace=workspace,
            status=TaskStatus.RUNNING,
            model=model,
            config=TaskConfig(max_turns=max_turns, model=model),
            max_turns=max_turns,
            agent_id=agent_id,
            session_id=session_id,
            started_at=datetime.now(),
        )

    # === 状态转换方法 ===

    def start(self) -> None:
        self.status = TaskStatus.RUNNING
        self.started_at = datetime.now()

    def complete(self, result: str) -> None:
        self.status = TaskStatus.COMPLETED
        self.result = result
        self.completed_at = datetime.now()

    def fail(self, error: str) -> None:
        self.status = TaskStatus.FAILED
        self.error = error
        self.completed_at = datetime.now()

    def cancel(self) -> None:
        self.status = TaskStatus.CANCELLED
        self.completed_at = datetime.now()
        self.error = "cancelled"

    def pause(self) -> None:
        self.status = TaskStatus.PAUSED

    # === 轮次管理 ===

    def increment_turn(self) -> bool:
        """递增当前轮次，返回是否可继续"""
        self.current_turn += 1
        return self.current_turn < self.max_turns

    # === 成本追踪 ===

    def add_cost(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        pricing: tuple[float, float] | None,
    ) -> None:
        self.cost = self.cost.add_tokens(prompt_tokens, completion_tokens, pricing)
