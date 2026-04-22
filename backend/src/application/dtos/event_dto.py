"""应用层 - SSE 事件 DTO"""

from datetime import datetime
from typing import Any, Dict

from pydantic import BaseModel, Field


class SSEEventDTO(BaseModel):
    """SSE 事件数据传输对象"""

    id: str = Field(..., description="事件序列号")
    event_type: str = Field(
        ...,
        description="事件类型（冒号分隔，SSE 输出时替换为连字符）",
        examples=["task:started", "llm:chunk", "tool:result"],
    )
    data: Dict[str, Any] = Field(..., description="事件载荷")
    timestamp: str = Field(..., description="ISO 8601 时间戳")

    @classmethod
    def create(
        cls, task_id: str, seq: int, event_type: str, payload: Dict[str, Any]
    ) -> "SSEEventDTO":
        """创建事件 DTO"""
        return cls(
            id=str(seq),
            event_type=event_type,
            data={**payload, "taskId": task_id},
            timestamp=datetime.now().isoformat(),
        )
