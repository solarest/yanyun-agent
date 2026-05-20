"""应用层 - Event 实体与 DTO 转换"""

from src.application.dtos.event_dto import SSEEventDTO
from src.domain.entities.event import Event


class EventMapper:
    """Event 实体与 DTO 之间的转换器

    职责：
    - 将领域层 Event 实体转换为应用层 DTO
    - 将应用层 DTO 转换为领域层 Event 实体
    - 保持领域层和应用层的解耦
    """

    @staticmethod
    def to_dto(entity: Event) -> SSEEventDTO:
        """将领域实体转换为 DTO

        Args:
            entity: Event 领域实体

        Returns:
            SSEEventDTO 实例
        """
        # 处理 timestamp 可能是字符串或 datetime 对象的情况
        if isinstance(entity.timestamp, str):
            timestamp_str = entity.timestamp
        else:
            timestamp_str = entity.timestamp.isoformat()

        return SSEEventDTO(
            id=entity.id,
            event_type=entity.event_type,
            data=entity.payload,
            timestamp=timestamp_str,
        )

    @staticmethod
    def to_entity(dto: SSEEventDTO) -> Event:
        """将 DTO 转换为领域实体

        Args:
            dto: SSEEventDTO 实例

        Returns:
            Event 领域实体
        """
        try:
            sequence = int(dto.id)
        except (ValueError, TypeError):
            sequence = 0

        return Event(
            event_type=dto.event_type,
            payload=dto.data,
            sequence=sequence,
            task_id=dto.data.get("taskId", ""),
            timestamp=dto.timestamp,
        )

    @staticmethod
    def to_dto_list(entities: list[Event]) -> list[SSEEventDTO]:
        """批量转换实体为 DTO"""
        return [EventMapper.to_dto(e) for e in entities]

    @staticmethod
    def to_entity_list(dtos: list[SSEEventDTO]) -> list[Event]:
        """批量转换 DTO 为实体"""
        return [EventMapper.to_entity(d) for d in dtos]
