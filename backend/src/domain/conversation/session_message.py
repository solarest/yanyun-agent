"""领域层 - SessionMessage 实体

用户可见的消息记录，与 LangGraph 内部 Message 区分。
一条 SessionMessage 对应用户视角的"一轮"对话。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from src.domain.base import Entity


class SessionMessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL_SUMMARY = "tool_summary"


class MessageStatus(str, Enum):
    COMPLETED = "completed"
    STREAMING = "streaming"
    ERROR = "error"


@dataclass
class SessionMessage(Entity):
    """会话消息实体"""

    session_id: str = ""
    task_id: Optional[str] = None
    role: SessionMessageRole = SessionMessageRole.USER
    content: str = ""
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    status: MessageStatus = MessageStatus.COMPLETED
    error: Optional[str] = None
    cost: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
