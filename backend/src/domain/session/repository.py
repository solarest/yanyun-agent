"""领域层 - Session Repository 接口"""

from abc import ABC, abstractmethod
from typing import List, Optional

from src.domain.session.entity import Session
from src.domain.session.message import SessionMessage


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


class ISessionMessageRepository(ABC):
    """会话消息仓储接口"""

    @abstractmethod
    async def get_by_id(self, message_id: str) -> Optional[SessionMessage]:
        """根据 ID 获取消息"""
        pass

    @abstractmethod
    async def add(self, message: SessionMessage) -> SessionMessage:
        """添加消息"""
        pass

    @abstractmethod
    async def update(self, message: SessionMessage) -> SessionMessage:
        """更新消息"""
        pass

    @abstractmethod
    async def list_by_session(
        self, session_id: str, limit: int = 50, offset: int = 0
    ) -> List[SessionMessage]:
        """获取某个会话的消息列表（按时间正序）"""
        pass

    @abstractmethod
    async def remove_by_session(self, session_id: str) -> int:
        """删除某个会话的所有消息，返回删除数量"""
        pass
