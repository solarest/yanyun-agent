"""领域层 - Event 实体

表示 SSE 流式事件的核心领域概念。
"""

from datetime import datetime
from typing import Any, Dict


class Event:
    """SSE 事件实体

    职责：
    - 封装事件的领域数据
    - 提供事件创建工厂方法
    - 保持领域层的纯净性
    """

    def __init__(
        self,
        event_type: str,
        payload: Dict[str, Any],
        sequence: int,
        task_id: str,
        timestamp: datetime | None = None,
    ):
        self.event_type = event_type
        self.payload = payload
        self.sequence = sequence
        self.task_id = task_id
        self.timestamp = timestamp or datetime.now()

    @property
    def id(self) -> str:
        """事件序列号（字符串格式）"""
        return str(self.sequence)

    @classmethod
    def create(
        cls,
        task_id: str,
        seq: int,
        event_type: str,
        payload: Dict[str, Any],
    ) -> "Event":
        """创建事件实体

        Args:
            task_id: 任务 ID
            seq: 事件序列号
            event_type: 事件类型
            payload: 事件载荷数据

        Returns:
            Event 实例
        """
        # 规范化事件类型为内部冒号风格
        normalized_type = event_type.replace("-", ":")
        # 在 payload 中添加 taskId
        enriched_payload = {**payload, "taskId": task_id}
        return cls(
            event_type=normalized_type,
            payload=enriched_payload,
            sequence=seq,
            task_id=task_id,
        )
