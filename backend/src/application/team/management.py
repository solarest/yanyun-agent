"""应用层 - Team 管理用例

编排 Team CRUD 操作：名称唯一性校验、成员管理。
"""

from datetime import datetime
from typing import Optional

from src.domain.team.entity import Team
from src.domain.team.member import TeamMember
from src.domain.team.repository import ITeamRepository
from src.domain.team.values import TeamRole, TeamStatus
from src.domain.agent.repository import IAgentRepository


class TeamManagementUseCase:
    """Team 管理用例

    职责：
    - 创建 Team（含名称唯一性校验 + 成员关联）
    - 查询 Team（列表/详情/成员）
    - 更新 Team
    - 删除 Team
    """

    def __init__(
        self,
        team_repo: ITeamRepository,
        agent_repo: IAgentRepository,
    ) -> None:
        self._team_repo = team_repo
        self._agent_repo = agent_repo

    async def create(
        self,
        name: str,
        leader_id: str,
        description: str = "",
        member_ids: Optional[list[str]] = None,
    ) -> Team:
        """创建 Team

        Args:
            name: 团队名称（唯一）
            leader_id: Leader Agent ID
            description: 团队描述
            member_ids: Member Agent IDs

        Returns:
            创建的 Team 实体

        Raises:
            DuplicateTeamNameError: 团队名称重复
            AgentNotFoundError: Leader/Member Agent 不存在
        """
        # 名称唯一性校验
        existing = await self._team_repo.get_by_name(name)
        if existing is not None:
            raise DuplicateTeamNameError(name)

        # 验证 Leader 存在
        leader = await self._agent_repo.get_by_id(leader_id)
        if leader is None:
            raise AgentNotFoundError(leader_id)

        member_ids = member_ids or []

        # 创建 Team
        team = Team(
            name=name,
            description=description,
            leader_id=leader_id,
            status=TeamStatus.IDLE,
            created_at=datetime.now(),
        )
        team = await self._team_repo.add(team)

        # 添加 Leader 成员
        leader_member = TeamMember(
            team_id=team.id,
            agent_id=leader_id,
            role=TeamRole.LEADER,
            status="idle",
            joined_at=datetime.now(),
        )
        await self._team_repo.add_member(leader_member)

        # 添加 Member 成员
        for member_id in member_ids:
            if member_id == leader_id:
                continue  # 跳过重复的 leader
            member_agent = await self._agent_repo.get_by_id(member_id)
            if member_agent is None:
                raise AgentNotFoundError(member_id)

            member = TeamMember(
                team_id=team.id,
                agent_id=member_id,
                role=TeamRole.MEMBER,
                status="idle",
                joined_at=datetime.now(),
            )
            await self._team_repo.add_member(member)

        return team

    async def get_by_id(self, team_id: str) -> Optional[Team]:
        """按 ID 获取 Team"""
        return await self._team_repo.get_by_id(team_id)

    async def list_all(self, page: int = 1, page_size: int = 20) -> tuple[list[Team], int]:
        """分页获取 Team 列表"""
        offset = (page - 1) * page_size
        teams = await self._team_repo.list_all(limit=page_size, offset=offset)
        # 简化：返回列表长度作为 total（后续可改为 COUNT 查询）
        return teams, len(teams)

    async def update(
        self,
        team_id: str,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        leader_id: Optional[str] = None,
        member_ids: Optional[list[str]] = None,
    ) -> Team:
        """更新 Team（PATCH 语义）"""
        team = await self._team_repo.get_by_id(team_id)
        if team is None:
            raise TeamNotFoundError(team_id)

        if name is not None and name != team.name:
            existing = await self._team_repo.get_by_name(name)
            if existing is not None:
                raise DuplicateTeamNameError(name)
            team.name = name

        if description is not None:
            team.description = description
        if leader_id is not None:
            team.leader_id = leader_id

        team.updated_at = datetime.now()
        team = await self._team_repo.update(team)

        # 更新成员列表
        if member_ids is not None:
            current_members = await self._team_repo.list_members(team_id)
            current_agent_ids = {m.agent_id for m in current_members}
            new_agent_ids = set(member_ids)

            # 添加新成员
            for agent_id in new_agent_ids - current_agent_ids:
                member = TeamMember(
                    team_id=team_id,
                    agent_id=agent_id,
                    role=TeamRole.MEMBER,
                )
                await self._team_repo.add_member(member)

            # 移除旧成员（保留 leader）
            leader_member = await self._team_repo.get_member(team_id, team.leader_id)
            for agent_id in current_agent_ids - new_agent_ids:
                if agent_id != team.leader_id:
                    await self._team_repo.remove_member(team_id, agent_id)

        return team

    async def delete(self, team_id: str) -> None:
        """删除 Team"""
        team = await self._team_repo.get_by_id(team_id)
        if team is None:
            raise TeamNotFoundError(team_id)
        await self._team_repo.remove(team_id)

    async def list_members(self, team_id: str) -> list[TeamMember]:
        """获取团队成员列表"""
        team = await self._team_repo.get_by_id(team_id)
        if team is None:
            raise TeamNotFoundError(team_id)
        return await self._team_repo.list_members(team_id)


# ── 业务异常 ──────────────────────────────────────────────


class TeamNotFoundError(Exception):
    """Team 不存在"""
    def __init__(self, team_id: str) -> None:
        self.team_id = team_id
        super().__init__(f"Team '{team_id}' not found")


class DuplicateTeamNameError(Exception):
    """Team 名称重复"""
    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"Team name '{name}' already exists")


class AgentNotFoundError(Exception):
    """Agent 不存在"""
    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        super().__init__(f"Agent '{agent_id}' not found")
