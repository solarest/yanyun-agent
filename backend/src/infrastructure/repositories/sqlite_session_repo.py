"""基础设施层 - SessionRepository SQLite 实现"""

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.session import Session, SessionStatus
from src.domain.repositories.session_repository import ISessionRepository
from src.infrastructure.database.models.agent_model import SessionModel


class SQLiteSessionRepository(ISessionRepository):
    """SQLite 会话仓储实现"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, session_id: str) -> Optional[Session]:
        result = await self.session.execute(
            select(SessionModel).where(SessionModel.id == session_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._to_entity(model)

    async def add(self, entity: Session) -> Session:
        model = self._to_model(entity)
        self.session.add(model)
        await self.session.commit()
        await self.session.refresh(model)
        return self._to_entity(model)

    async def update(self, entity: Session) -> Session:
        result = await self.session.execute(
            select(SessionModel).where(SessionModel.id == entity.id)
        )
        model = result.scalar_one_or_none()
        if not model:
            raise ValueError(f"Session {entity.id} not found")

        model.title = entity.title
        model.status = entity.status.value
        model.message_count = entity.message_count
        model.last_message_preview = entity.last_message_preview
        model.updated_at = entity.updated_at

        await self.session.commit()
        await self.session.refresh(model)
        return self._to_entity(model)

    async def remove(self, session_id: str) -> bool:
        result = await self.session.execute(
            select(SessionModel).where(SessionModel.id == session_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return False

        await self.session.delete(model)
        await self.session.commit()
        return True

    async def list_by_agent(self, agent_id: str, limit: int = 50, offset: int = 0) -> List[Session]:
        result = await self.session.execute(
            select(SessionModel)
            .where(SessionModel.agent_id == agent_id)
            .order_by(SessionModel.updated_at.desc().nullslast(), SessionModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        models = result.scalars().all()
        return [self._to_entity(m) for m in models]

    def _to_entity(self, model: SessionModel) -> Session:
        return Session(
            id=model.id,
            agent_id=model.agent_id,
            title=model.title,
            status=SessionStatus(model.status),
            message_count=model.message_count,
            last_message_preview=model.last_message_preview,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_model(self, entity: Session) -> SessionModel:
        return SessionModel(
            id=entity.id,
            agent_id=entity.agent_id,
            title=entity.title,
            status=entity.status.value,
            message_count=entity.message_count,
            last_message_preview=entity.last_message_preview,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )
