"""领域层 - Team Repository 接口"""

from abc import ABC, abstractmethod
from typing import Optional

from src.domain.team.entity import Team
from src.domain.team.member import TeamMember


class ITeamRepository(ABC):
    """Team 仓储接口"""

    @abstractmethod
    async def get_by_id(self, team_id: str) -> Optional[Team]:
        """根据 ID 获取 Team"""
        ...

    @abstractmethod
    async def get_by_name(self, name: str) -> Optional[Team]:
        """根据名称获取 Team（用于唯一性校验）"""
        ...

    @abstractmethod
    async def add(self, team: Team) -> Team:
        """新增 Team"""
        ...

    @abstractmethod
    async def update(self, team: Team) -> Team:
        """更新 Team"""
        ...

    @abstractmethod
    async def remove(self, team_id: str) -> bool:
        """删除 Team"""
        ...

    @abstractmethod
    async def list_all(self, limit: int = 100, offset: int = 0) -> list[Team]:
        """获取 Team 列表"""
        ...

    @abstractmethod
    async def list_members(self, team_id: str) -> list[TeamMember]:
        """获取团队成员列表"""
        ...

    @abstractmethod
    async def add_member(self, member: TeamMember) -> TeamMember:
        """添加团队成员"""
        ...

    @abstractmethod
    async def remove_member(self, team_id: str, agent_id: str) -> bool:
        """移除团队成员"""
        ...

    @abstractmethod
    async def get_member(self, team_id: str, agent_id: str) -> Optional[TeamMember]:
        """获取指定团队成员"""
        ...
