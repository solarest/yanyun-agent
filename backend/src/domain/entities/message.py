"""领域层 - Message 实体"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from src.domain.entities.base import Entity


class MessageRole(str, Enum):
    """消息角色枚举"""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class MessageVisibility(str, Enum):
    """消息可见性枚举"""

    USER_VISIBLE = "user_visible"
    AGENT_VISIBLE = "agent_visible"


@dataclass
class Message(Entity):
    """消息实体 (对话历史)"""

    task_id: str = ""
    role: MessageRole = MessageRole.USER
    content: str = ""
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    tool_call_id: Optional[str] = None  # tool 角色关联的工具调用 ID
    visibility: MessageVisibility = MessageVisibility.USER_VISIBLE
    token_count: int = 0
    created_at: datetime = field(default_factory=datetime.now)
