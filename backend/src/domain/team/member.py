"""领域层 - TeamMember 实体"""

from dataclasses import dataclass, field
from datetime import datetime

from src.domain.entities.base import Entity
from src.domain.team.values import TeamRole


@dataclass
class TeamMember(Entity):
    """TeamMember 领域实体

    将一个 Agent 关联到 Team，并指定角色和当前状态。

    Attributes:
        team_id: 所属团队 ID
        agent_id: Agent ID
        role: 团队角色（leader / member）
        status: 成员当前状态（idle / busy / done）
        joined_at: 加入时间
    """

    team_id: str = ""
    agent_id: str = ""
    role: TeamRole = TeamRole.MEMBER
    status: str = "idle"  # idle | busy | done

    joined_at: datetime = field(default_factory=datetime.now)
