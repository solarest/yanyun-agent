"""领域层 - Team 实体"""

from dataclasses import dataclass, field
from datetime import datetime

from src.domain.entities.base import Entity
from src.domain.team.values import TeamStatus


@dataclass
class Team(Entity):
    """Team 领域实体

    定义一个由多个 Agent 组成的协作团队，包含 leader、members 和当前执行目标。

    Attributes:
        name: 团队名称（唯一）
        description: 团队描述
        leader_id: 团队 leader 的 Agent ID
        goal: 当前团队执行目标
        status: 团队执行状态
        config: 团队级配置（JSON）
        created_at: 创建时间
        updated_at: 更新时间
    """

    name: str = ""
    description: str = ""
    leader_id: str = ""
    goal: str = ""
    status: TeamStatus = TeamStatus.IDLE
    config: dict = field(default_factory=dict)

    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime | None = None
