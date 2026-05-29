"""Agent 聚合的领域事件。"""

from dataclasses import dataclass, field

from src.domain.events.base import DomainEvent


@dataclass(frozen=True)
class AgentCreated(DomainEvent):
    """Agent 已创建"""

    agent_id: str = ""
    agent_name: str = ""


@dataclass(frozen=True)
class AgentConfigUpdated(DomainEvent):
    """Agent 配置已更新"""

    agent_id: str = ""
    config_version: int = 0
    updated_fields: tuple[str, ...] = field(default_factory=tuple)
