"""领域层 - Task 实体"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from src.domain.entities.base import Entity


class TaskStatus(str, Enum):
    """任务状态枚举"""

    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


@dataclass
class TaskConfig:
    """任务配置"""

    max_turns: int = 100
    model: str = "gpt-4"
    temperature: float = 0.7


# 模型定价表（每 1K tokens，美元）
_MODEL_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4": (0.03, 0.06),
    "gpt-4-turbo": (0.01, 0.03),
    "gpt-3.5-turbo": (0.0005, 0.0015),
    "gpt-4o": (0.005, 0.015),
    "gpt-4o-mini": (0.00015, 0.0006),
    "claude-3-opus": (0.015, 0.075),
    "claude-3-sonnet": (0.003, 0.015),
    "claude-3-haiku": (0.00025, 0.00125),
    "claude-3-5-sonnet": (0.003, 0.015),
}


@dataclass
class CostTracker:
    """成本追踪器"""

    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_cost: float = 0.0

    def add_tokens(self, prompt_tokens: int, completion_tokens: int, model: str) -> None:
        """累加 Token 并计算成本

        Args:
            prompt_tokens: 输入 token 数
            completion_tokens: 输出 token 数
            model: 模型名称
        """
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.total_tokens = self.prompt_tokens + self.completion_tokens

        # 计算成本
        pricing = _MODEL_PRICING.get(model)
        if pricing is None:
            # 尝试前缀匹配
            for key, price in _MODEL_PRICING.items():
                if model.startswith(key):
                    pricing = price
                    break

        if pricing:
            prompt_price, completion_price = pricing
            self.total_cost += (prompt_tokens / 1000 * prompt_price) + (
                completion_tokens / 1000 * completion_price
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_tokens": self.total_tokens,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_cost": self.total_cost,
        }


@dataclass
class Task(Entity):
    """Agent 任务实体"""

    message: str = ""  # 用户输入的任务描述
    workspace: str = ""  # 工作目录路径
    status: TaskStatus = TaskStatus.IDLE  # 任务状态
    model: str = ""  # 使用的模型标识
    config: TaskConfig = field(default_factory=TaskConfig)
    current_turn: int = 0  # 当前轮次
    max_turns: int = 100  # 最大轮次
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[str] = None  # 最终结果
    error: Optional[str] = None  # 错误信息
    cost: CostTracker = field(default_factory=CostTracker)
    agent_id: Optional[str] = None  # 关联的 Agent ID
    session_id: Optional[str] = None  # 关联的 Session ID
