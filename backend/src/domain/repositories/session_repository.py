"""领域层 - SessionRepository 接口"""

from abc import ABC, abstractmethod
from typing import List, Optional

from src.domain.aggregates.session.session import Session


class ISessionRepository(ABC):
    """会话仓储接口"""

    @abstractmethod
    async def get_by_id(self, session_id: str) -> Optional[Session]:
        """根据 ID 获取会话"""
        pass

    @abstractmethod
    async def add(self, session: Session) -> Session:
        """添加会话"""
        pass

    @abstractmethod
    async def update(self, session: Session) -> Session:
        """更新会话"""
        pass

    @abstractmethod
    async def remove(self, session_id: str) -> bool:
        """删除会话"""
        pass

    @abstractmethod
    async def list_by_agent(self, agent_id: str, limit: int = 50, offset: int = 0) -> List[Session]:
        """获取某个 Agent 的会话列表"""
        pass
