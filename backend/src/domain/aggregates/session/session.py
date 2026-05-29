"""领域层 - Session 实体

会话容器，属于某个 Agent，包含多轮消息。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from src.domain.entities.base import Entity


class SessionStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


@dataclass
class Session(Entity):
    """Agent 会话实体"""

    agent_id: str = ""
    title: str = ""
    status: SessionStatus = SessionStatus.ACTIVE
    message_count: int = 0
    last_message_preview: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime | None = None

    def update_metadata(self, content: str) -> None:
        """更新会话元数据（消息计数和预览）"""
        self.message_count += 1
        self.last_message_preview = content[:100] if content else ""
        self.updated_at = datetime.now()

    def auto_title(self, first_message: str) -> None:
        """从首条消息自动生成标题"""
        if not self.title:
            self.title = first_message[:50].strip()
            if len(first_message) > 50:
                self.title += "..."

    def archive(self) -> None:
        """归档会话"""
        self.status = SessionStatus.ARCHIVED
        self.updated_at = datetime.now()

    @classmethod
    def create(cls, agent_id: str, title: str = "") -> "Session":
        """创建新会话（工厂方法）"""
        return cls(
            agent_id=agent_id,
            title=title,
            status=SessionStatus.ACTIVE,
        )
