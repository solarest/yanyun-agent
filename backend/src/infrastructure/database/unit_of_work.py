"""基础设施层 - SQLAlchemy 工作单元实现

为每个业务操作提供事务边界，确保跨聚合操作的原子性。
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.repositories.unit_of_work import IUnitOfWork
from src.infrastructure.database.session import AsyncSessionLocal
from src.infrastructure.repositories.sqlite_agent_repo import SQLiteAgentRepository
from src.infrastructure.repositories.sqlite_session_repo import SQLiteSessionRepository
from src.infrastructure.repositories.sqlite_session_message_repo import (
    SQLiteSessionMessageRepository,
)
from src.infrastructure.repositories.sqlite_skill_repo import SQLiteSkillRepository
from src.infrastructure.repositories.sqlite_task_repo import SQLiteTaskRepository

logger = logging.getLogger(__name__)


class SqlAlchemyUnitOfWork(IUnitOfWork):
    """SQLAlchemy 工作单元 — 管理事务和仓储生命周期"""

    def __init__(self, session: AsyncSession | None = None):
        self._session = session
        self._owns_session = session is None

    async def __aenter__(self) -> "SqlAlchemyUnitOfWork":
        if self._session is None:
            self._session = AsyncSessionLocal()
        self._agent_repo = SQLiteAgentRepository(self._session)
        self._task_repo = SQLiteTaskRepository(self._session)
        self._session_repo = SQLiteSessionRepository(self._session)
        self._session_message_repo = SQLiteSessionMessageRepository(self._session)
        self._skill_repo = SQLiteSkillRepository(self._session)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        try:
            if exc_type is not None:
                await self.rollback()
            else:
                await self.commit()
        finally:
            if self._owns_session and self._session is not None:
                await self._session.close()

    @property
    def agents(self) -> SQLiteAgentRepository:
        return self._agent_repo

    @property
    def tasks(self) -> SQLiteTaskRepository:
        return self._task_repo

    @property
    def sessions(self) -> SQLiteSessionRepository:
        return self._session_repo

    @property
    def session_messages(self) -> SQLiteSessionMessageRepository:
        return self._session_message_repo

    @property
    def skills(self) -> SQLiteSkillRepository:
        return self._skill_repo

    async def commit(self) -> None:
        if self._session is not None:
            await self._session.commit()

    async def rollback(self) -> None:
        if self._session is not None:
            await self._session.rollback()
