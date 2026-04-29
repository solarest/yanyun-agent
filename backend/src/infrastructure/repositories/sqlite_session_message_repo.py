"""基础设施层 - SessionMessageRepository SQLite 实现"""

from typing import List, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.session_message import (
    MessageStatus,
    SessionMessage,
    SessionMessageRole,
)
from src.domain.repositories.session_message_repository import (
    ISessionMessageRepository,
)
from src.infrastructure.database.models.agent_model import SessionMessageModel


class SQLiteSessionMessageRepository(ISessionMessageRepository):
    """SQLite 会话消息仓储实现"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, message_id: str) -> Optional[SessionMessage]:
        result = await self.session.execute(
            select(SessionMessageModel).where(SessionMessageModel.id == message_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._to_entity(model)

    async def add(self, entity: SessionMessage) -> SessionMessage:
        model = self._to_model(entity)
        self.session.add(model)
        await self.session.commit()
        await self.session.refresh(model)
        return self._to_entity(model)

    async def update(self, entity: SessionMessage) -> SessionMessage:
        result = await self.session.execute(
            select(SessionMessageModel).where(SessionMessageModel.id == entity.id)
        )
        model = result.scalar_one_or_none()
        if not model:
            raise ValueError(f"SessionMessage {entity.id} not found")

        model.content = entity.content
        model.tool_calls = entity.tool_calls
        model.tool_results = entity.tool_results
        model.status = entity.status.value
        model.error = entity.error
        model.cost = entity.cost
        model.task_id = entity.task_id

        await self.session.commit()
        await self.session.refresh(model)
        return self._to_entity(model)

    async def list_by_session(
        self, session_id: str, limit: int = 50, offset: int = 0
    ) -> List[SessionMessage]:
        result = await self.session.execute(
            select(SessionMessageModel)
            .where(SessionMessageModel.session_id == session_id)
            .order_by(SessionMessageModel.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        models = result.scalars().all()
        return [self._to_entity(m) for m in models]

    async def remove_by_session(self, session_id: str) -> int:
        result = await self.session.execute(
            delete(SessionMessageModel).where(SessionMessageModel.session_id == session_id)
        )
        await self.session.commit()
        return result.rowcount

    def _to_entity(self, model: SessionMessageModel) -> SessionMessage:
        return SessionMessage(
            id=model.id,
            session_id=model.session_id,
            task_id=model.task_id,
            role=SessionMessageRole(model.role),
            content=model.content,
            tool_calls=model.tool_calls or [],
            tool_results=model.tool_results or [],
            status=MessageStatus(model.status),
            error=model.error,
            cost=model.cost or {},
            created_at=model.created_at,
        )

    def _to_model(self, entity: SessionMessage) -> SessionMessageModel:
        return SessionMessageModel(
            id=entity.id,
            session_id=entity.session_id,
            task_id=entity.task_id,
            role=entity.role.value,
            content=entity.content,
            tool_calls=entity.tool_calls,
            tool_results=entity.tool_results,
            status=entity.status.value,
            error=entity.error,
            cost=entity.cost,
            created_at=entity.created_at,
        )
