"""基础设施层 - EventRepository SQLite 实现"""

from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.dtos.event_dto import SSEEventDTO
from src.domain.repositories.event_repository import IEventRepository
from src.infrastructure.database.models.agent_model import EventModel


class SQLiteEventRepository(IEventRepository):
    """SQLite 事件仓储实现"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def save(self, task_id: str, event: SSEEventDTO) -> None:
        """保存事件"""
        model = EventModel(
            task_id=task_id,
            event_type=event.event_type,
            event_data=event.data,
        )
        self.session.add(model)
        await self.session.commit()

    async def get_after(self, task_id: str, last_event_id: str) -> List[SSEEventDTO]:
        """获取指定序列号之后的事件"""
        result = await self.session.execute(
            select(EventModel)
            .where(EventModel.task_id == task_id)
            .where(EventModel.id > int(last_event_id))
            .order_by(EventModel.id.asc())
        )
        models = result.scalars().all()
        return [self._to_dto(m) for m in models]

    async def get_by_task_id(self, task_id: str) -> List[SSEEventDTO]:
        """获取任务的所有事件"""
        result = await self.session.execute(
            select(EventModel).where(EventModel.task_id == task_id).order_by(EventModel.id.asc())
        )
        models = result.scalars().all()
        return [self._to_dto(m) for m in models]

    def _to_dto(self, model: EventModel) -> SSEEventDTO:
        """数据库模型转 DTO"""
        return SSEEventDTO(
            id=str(model.id),
            event_type=model.event_type,
            data=model.event_data,
            timestamp=model.created_at.isoformat(),
        )
