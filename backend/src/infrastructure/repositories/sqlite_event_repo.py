"""基础设施层 - EventRepository SQLite 实现"""

from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.dtos.event_dto import SSEEventDTO, normalize_event_type
from src.domain.repositories.event_repository import IEventRepository
from src.infrastructure.database.models.agent_model import EventModel


class SQLiteEventRepository(IEventRepository):
    """SQLite 事件仓储实现

    注意：对外暴露的 SSEEventDTO.id 使用 EventModel.task_seq（任务级序号），
    而非数据库自增主键 EventModel.id，以保证回放事件与实时事件 id 体系一致，
    避免 sse_stream 跳过逻辑误丢实时事件。
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def save(self, task_id: str, event: SSEEventDTO) -> None:
        """保存事件（task_seq 由 SSEEventDTO.id 解析得到）"""
        try:
            seq = int(event.id)
        except (TypeError, ValueError):
            seq = 0
        model = EventModel(
            task_id=task_id,
            task_seq=seq,
            event_type=normalize_event_type(event.event_type),
            event_data=event.data,
        )
        self.session.add(model)
        await self.session.commit()

    async def save_batch(self, task_id: str, events: List[SSEEventDTO]) -> None:
        """批量保存事件。"""
        if not events:
            return

        models: list[EventModel] = []
        for event in events:
            try:
                seq = int(event.id)
            except (TypeError, ValueError):
                seq = 0
            models.append(
                EventModel(
                    task_id=task_id,
                    task_seq=seq,
                    event_type=normalize_event_type(event.event_type),
                    event_data=event.data,
                )
            )

        self.session.add_all(models)
        await self.session.commit()

    async def get_after(self, task_id: str, last_event_id: str) -> List[SSEEventDTO]:
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
        return [self._to_dto(m) for m in models]

    async def get_by_task_id(self, task_id: str) -> List[SSEEventDTO]:
        """获取任务的所有事件，按任务级序号升序"""
        result = await self.session.execute(
            select(EventModel)
            .where(EventModel.task_id == task_id)
            .order_by(EventModel.task_seq.asc())
        )
        models = result.scalars().all()
        return [self._to_dto(m) for m in models]

    def _to_dto(self, model: EventModel) -> SSEEventDTO:
        """数据库模型转 DTO（id 取 task_seq，与实时事件保持同一体系）"""
        return SSEEventDTO(
            id=str(model.task_seq),
            event_type=normalize_event_type(model.event_type),
            data=model.event_data,
            timestamp=model.created_at.isoformat(),
        )
