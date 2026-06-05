"""领域层 - TeamMessage 实体"""

from dataclasses import dataclass, field
from datetime import datetime

from src.domain.entities.base import Entity
from src.domain.team.values import MessageType


@dataclass
class TeamMessage(Entity):
    """TeamMessage 领域实体

    团队消息总线上的一条消息，用于 Leader ↔ Member 之间的结构化通信。

    Attributes:
        team_id: 所属团队 ID
        sender_agent_id: 发送方 Agent ID
        receiver_agent_id: 接收方 Agent ID（或 "leader"）
        message_type: 消息类型
        content: 消息内容
        request_id: 请求 ID（用于 request-response 关联，参考 s16 协议模式）
        created_at: 创建时间
        read_at: 被读取时间
    """

    team_id: str = ""
    sender_agent_id: str = ""
    receiver_agent_id: str = ""
    message_type: MessageType = MessageType.TASK_ASSIGN
    content: str = ""
    request_id: str | None = None

    created_at: datetime = field(default_factory=datetime.now)
    read_at: datetime | None = None
