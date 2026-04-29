"""应用层 - Session 管理用例"""

from typing import List, Optional

from src.domain.entities.session import Session, SessionStatus
from src.domain.repositories.session_repository import ISessionRepository
from src.domain.repositories.session_message_repository import ISessionMessageRepository


class SessionManagementUseCase:
    """会话 CRUD 用例"""

    def __init__(
        self,
        session_repo: ISessionRepository,
        message_repo: ISessionMessageRepository,
    ):
        self.session_repo = session_repo
        self.message_repo = message_repo

    async def create_session(self, agent_id: str, title: Optional[str] = None) -> Session:
        session = Session(
            agent_id=agent_id,
            title=title or "",
            status=SessionStatus.ACTIVE,
        )
        return await self.session_repo.add(session)

    async def get_session(self, session_id: str) -> Optional[Session]:
        return await self.session_repo.get_by_id(session_id)

    async def list_sessions(self, agent_id: str, limit: int = 50, offset: int = 0) -> List[Session]:
        return await self.session_repo.list_by_agent(agent_id, limit, offset)

    async def update_session(
        self,
        session_id: str,
        title: Optional[str] = None,
        status: Optional[str] = None,
    ) -> Optional[Session]:
        session = await self.session_repo.get_by_id(session_id)
        if not session:
            return None

        if title is not None:
            session.title = title
        if status is not None:
            session.status = SessionStatus(status)

        from datetime import datetime

        session.updated_at = datetime.now()
        return await self.session_repo.update(session)

    async def delete_session(self, session_id: str) -> bool:
        # 先删除该会话的所有消息
        await self.message_repo.remove_by_session(session_id)
        return await self.session_repo.remove(session_id)
