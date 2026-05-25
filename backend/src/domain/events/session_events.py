"""Session 聚合的领域事件。"""

from dataclasses import dataclass

from src.domain.events.base import DomainEvent


@dataclass(frozen=True)
class SessionStarted(DomainEvent):
    """会话已开始"""

    session_id: str = ""
    agent_id: str = ""


@dataclass(frozen=True)
class MessageSent(DomainEvent):
    """消息已发送"""

    message_id: str = ""
    session_id: str = ""
    task_id: str = ""
    role: str = ""
