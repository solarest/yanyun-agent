"""应用层 - SSE 事件 DTO"""

from datetime import datetime
from typing import Any, Dict

from pydantic import BaseModel, Field


def normalize_event_type(event_type: str) -> str:
    """规范化事件类型为内部冒号风格。"""
    return event_type.replace("-", ":")


def to_sse_event_name(event_type: str) -> str:
    """将内部事件名转换为 SSE 协议层事件名。"""
    return normalize_event_type(event_type).replace(":", "-")


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
        normalized_type = normalize_event_type(event_type)
        return cls(
            id=str(seq),
            event_type=normalized_type,
            data={**payload, "taskId": task_id},
            timestamp=datetime.now().isoformat(),
        )
