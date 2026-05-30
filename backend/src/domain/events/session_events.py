"""Session 聚合的领域事件。"""

from dataclasses import dataclass

from src.domain.events.base import DomainEvent


@dataclass(frozen=True)
class SessionStarted(DomainEvent):
    """会话已开始"""

    session_id: str = ""
    agent_id: str = ""
