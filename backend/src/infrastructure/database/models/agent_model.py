"""基础设施层 - SQLAlchemy 数据库模型"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, JSON, String, Text
from src.infrastructure.database.session import Base


class TaskModel(Base):
    """任务数据库模型"""

    __tablename__ = "tasks"

    id = Column(String, primary_key=True)
    message = Column(Text, nullable=False)
    workspace = Column(String, nullable=False)
    status = Column(String, default="idle", nullable=False)
    model = Column(String, default="", nullable=False)
    config = Column(JSON, default={})
    current_turn = Column(Integer, default=0)
    max_turns = Column(Integer, default=100)
    result = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    cost = Column(JSON, default={})
    agent_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<TaskModel(id={self.id}, status={self.status})>"


class EventModel(Base):
    """SSE 事件数据库模型"""

    __tablename__ = "sse_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String, nullable=False, index=True)
    event_type = Column(String, nullable=False)
    event_data = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<EventModel(id={self.id}, task_id={self.task_id}, type={self.event_type})>"


class AgentModel(Base):
    """Agent 数据库模型"""

    __tablename__ = "agents"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False, unique=True, index=True)
    role = Column(Text, nullable=False)
    system_prompt_template = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<AgentModel(id={self.id}, name={self.name})>"
