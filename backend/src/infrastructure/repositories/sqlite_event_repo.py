"""基础设施层 - EventRepository SQLite 实现"""

from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.services.event_utils import normalize_event_type
from src.domain.entities.event import Event
from src.domain.repositories.event_repository import IEventRepository
from src.infrastructure.database.models.agent_model import EventModel


class SQLiteEventRepository(IEventRepository):
    """SQLite 事件仓储实现

    注意：事件序列号使用 EventModel.task_seq（任务级序号），
    而非数据库自增主键 EventModel.id，以保证回放事件与实时事件 id 体系一致。
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def save(self, task_id: str, event: Event) -> None:
        """保存事件（task_seq 由 Event.sequence 解析得到）"""
        model = EventModel(
            task_id=task_id,
            task_seq=event.sequence,
            event_type=normalize_event_type(event.event_type),
            event_data=event.payload,
        )
        self.session.add(model)
        await self.session.commit()

    async def save_batch(self, task_id: str, events: List[Event]) -> None:
        """批量保存事件。"""
        if not events:
            return

        models: list[EventModel] = []
        for event in events:
            models.append(
                EventModel(
                    task_id=task_id,
                    task_seq=event.sequence,
                    event_type=normalize_event_type(event.event_type),
                    event_data=event.payload,
                )
            )

        self.session.add_all(models)
        await self.session.commit()

    async def get_after(self, task_id: str, last_event_id: str) -> List[Event]:
        """获取指定任务级序号之后的事件"""
        try:
            last_seq = int(last_event_id)
        except (TypeError, ValueError):
            last_seq = 0
        result = await self.session.execute(
            select(EventModel)
            .where(EventModel.task_id == task_id)
            .where(EventModel.task_seq > last_seq)
            .order_by(EventModel.task_seq.asc())
        )
        models = result.scalars().all()
        return [self._to_entity(m) for m in models]

    async def get_by_task_id(self, task_id: str) -> List[Event]:
        """获取任务的所有事件，按任务级序号升序"""
        result = await self.session.execute(
            select(EventModel)
            .where(EventModel.task_id == task_id)
            .order_by(EventModel.task_seq.asc())
        )
        models = result.scalars().all()
        return [self._to_entity(m) for m in models]

    def _to_entity(self, model: EventModel) -> Event:
        """数据库模型转领域实体"""
        return Event(
            event_type=normalize_event_type(model.event_type),
            payload=model.event_data,
            sequence=model.task_seq,
            task_id=model.task_id,
            timestamp=model.created_at,
        )
