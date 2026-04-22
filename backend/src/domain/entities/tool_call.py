"""领域层 - ToolCall 实体"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from src.domain.entities.base import BaseEntity


class ToolCallState(str, Enum):
    """工具调用状态"""
    VALIDATING = "validating"
    SCHEDULED = "scheduled"
    EXECUTING = "executing"
    SUCCESS = "success"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class ToolCall(BaseEntity):
    """工具调用实体"""
    task_id: str = ""                          # 关联任务 ID
    name: str = ""                             # 工具名称
    input: Dict[str, Any] = field(default_factory=dict)  # 输入参数
    state: ToolCallState = ToolCallState.VALIDATING
    result: Optional[str] = None
    error: Optional[str] = None
    error_type: Optional[str] = None           # recoverable/fatal/timeout
    duration_ms: int = 0
    created_at: datetime = field(default_factory=datetime.now)
