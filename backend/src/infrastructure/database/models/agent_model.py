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
    session_id = Column(String, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<TaskModel(id={self.id}, status={self.status})>"


class EventModel(Base):
    """SSE 事件数据库模型"""

    __tablename__ = "sse_events"

    # 数据库自增主键（用于排序与索引，不对外暴露）
    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String, nullable=False, index=True)
    # 任务级别的事件序号（每个 task 从 1 开始递增），与 SSEEventDTO.id 对应
    task_seq = Column(Integer, nullable=False, default=0)
    event_type = Column(String, nullable=False)
    event_data = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<EventModel(id={self.id}, task_id={self.task_id}, seq={self.task_seq}, type={self.event_type})>"


class AgentModel(Base):
    """Agent 数据库模型 - 单表设计（OpenClaw 七文件模式）"""

    __tablename__ = "agents"

    # 主键
    id = Column(String(36), primary_key=True)

    # 基本信息
    name = Column(String(100), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=False, default="")

    # 简化表单创建器字段
    vibes = Column(Text, nullable=False, default="[]")  # JSON 数组

    # 配置文件内容（OpenClaw 七文件模式）
    identity_md = Column(Text, nullable=False, default="")  # IDENTITY.md
    soul_md = Column(Text, nullable=False, default="")  # SOUL.md
    agents_md = Column(Text, nullable=False, default="")  # AGENTS.md
    bootstrap_md = Column(Text, nullable=False, default="")  # BOOTSTRAP.md
    memory_md = Column(Text, nullable=False, default="")  # MEMORY.md
    tools_md = Column(Text, nullable=False, default="")  # TOOLS.md
    user_md = Column(Text, nullable=False, default="")  # USER.md

    # 版本管理
    config_version = Column(Integer, nullable=False, default=1)

    # 时间戳
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<AgentModel(id={self.id}, name={self.name}, version={self.config_version})>"


class SessionModel(Base):
    """会话数据库模型"""

    __tablename__ = "sessions"

    id = Column(String(36), primary_key=True)
    agent_id = Column(String(36), nullable=False, index=True)
    title = Column(String(200), nullable=False, default="")
    status = Column(String(20), nullable=False, default="active")
    message_count = Column(Integer, nullable=False, default=0)
    last_message_preview = Column(String(200), nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<SessionModel(id={self.id}, agent_id={self.agent_id})>"


class SkillModel(Base):
    """Skill 数据库模型"""

    __tablename__ = "skills"

    id = Column(String(36), primary_key=True)
    name = Column(String(100), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=False, default="")
    content = Column(Text, nullable=False, default="")
    file_path = Column(String(500), nullable=True, default="")
    trigger_keywords = Column(Text, nullable=False, default="[]")  # JSON 数组
    steps = Column(Text, nullable=False, default="[]")  # JSON 数组
    category = Column(String(50), nullable=False, default="general")
    enabled = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<SkillModel(id={self.id}, name={self.name}, enabled={self.enabled})>"


class SessionMessageModel(Base):
    """会话消息数据库模型"""

    __tablename__ = "session_messages"

    id = Column(String(36), primary_key=True)
    session_id = Column(String(36), nullable=False, index=True)
    task_id = Column(String(36), nullable=True)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False, default="")
    thinking_content = Column(Text, nullable=False, default="")
    tool_calls = Column(JSON, default=[])
    tool_results = Column(JSON, default=[])
    status = Column(String(20), nullable=False, default="completed")
    error = Column(Text, nullable=True)
    cost = Column(JSON, default={})
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<SessionMessageModel(id={self.id}, role={self.role})>"
