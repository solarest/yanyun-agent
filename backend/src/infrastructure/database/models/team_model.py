"""基础设施层 - Team 数据库模型"""

from datetime import datetime

from sqlalchemy import Column, DateTime, JSON, String, Text
from src.infrastructure.database.session import Base


class TeamModel(Base):
    """团队数据库模型"""

    __tablename__ = "teams"

    id = Column(String(36), primary_key=True)
    name = Column(String(100), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=False, default="")
    leader_id = Column(String(36), nullable=False, index=True)
    goal = Column(Text, nullable=False, default="")
    status = Column(String(20), nullable=False, default="idle")
    config = Column(JSON, default={})
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<TeamModel(id={self.id}, name={self.name}, status={self.status})>"


class TeamMemberModel(Base):
    """团队成员数据库模型"""

    __tablename__ = "team_members"

    id = Column(String(36), primary_key=True)
    team_id = Column(String(36), nullable=False, index=True)
    agent_id = Column(String(36), nullable=False, index=True)
    role = Column(String(20), nullable=False, default="member")
    status = Column(String(20), nullable=False, default="idle")
    joined_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<TeamMemberModel(id={self.id}, team_id={self.team_id}, agent_id={self.agent_id}, role={self.role})>"


class TeamMessageModel(Base):
    """团队消息数据库模型"""

    __tablename__ = "team_messages"

    id = Column(String(36), primary_key=True)
    team_id = Column(String(36), nullable=False, index=True)
    sender_agent_id = Column(String(36), nullable=False)
    receiver_agent_id = Column(String(36), nullable=False)
    message_type = Column(String(20), nullable=False)
    content = Column(Text, nullable=False, default="")
    request_id = Column(String(36), nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    read_at = Column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<TeamMessageModel(id={self.id}, type={self.message_type}, sender={self.sender_agent_id})>"
