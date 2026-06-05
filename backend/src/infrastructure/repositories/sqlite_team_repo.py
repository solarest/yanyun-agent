"""基础设施层 - TeamRepository SQLite 实现"""

from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.team.entity import Team
from src.domain.team.member import TeamMember
from src.domain.team.repository import ITeamRepository
from src.domain.team.values import TeamRole, TeamStatus
from src.infrastructure.database.models.team_model import TeamModel, TeamMemberModel


class SQLiteTeamRepository(ITeamRepository):
    """SQLite Team 仓储实现"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Team CRUD ──────────────────────────────────────────

    async def get_by_id(self, team_id: str) -> Optional[Team]:
        result = await self.session.execute(
            select(TeamModel).where(TeamModel.id == team_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._team_to_entity(model)

    async def get_by_name(self, name: str) -> Optional[Team]:
        result = await self.session.execute(
            select(TeamModel).where(TeamModel.name == name)
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._team_to_entity(model)

    async def add(self, team: Team) -> Team:
        model = self._team_to_model(team)
        self.session.add(model)
        await self.session.commit()
        await self.session.refresh(model)
        return self._team_to_entity(model)

    async def update(self, team: Team) -> Team:
        result = await self.session.execute(
            select(TeamModel).where(TeamModel.id == team.id)
        )
        model = result.scalar_one_or_none()
        if not model:
            raise ValueError(f"Team {team.id} not found")

        model.name = team.name
        model.description = team.description
        model.leader_id = team.leader_id
        model.goal = team.goal
        model.status = team.status.value if isinstance(team.status, TeamStatus) else team.status
        model.config = team.config
        model.updated_at = team.updated_at

        await self.session.commit()
        await self.session.refresh(model)
        return self._team_to_entity(model)

    async def remove(self, team_id: str) -> bool:
        result = await self.session.execute(
            select(TeamModel).where(TeamModel.id == team_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return False

        # 级联删除成员
        await self.session.execute(
            delete(TeamMemberModel).where(TeamMemberModel.team_id == team_id)
        )
        await self.session.delete(model)
        await self.session.commit()
        return True

    async def list_all(self, limit: int = 100, offset: int = 0) -> list[Team]:
        result = await self.session.execute(
            select(TeamModel)
            .order_by(TeamModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        models = result.scalars().all()
        return [self._team_to_entity(m) for m in models]

    # ── Member CRUD ───────────────────────────────────────

    async def list_members(self, team_id: str) -> list[TeamMember]:
        result = await self.session.execute(
            select(TeamMemberModel).where(TeamMemberModel.team_id == team_id)
        )
        models = result.scalars().all()
        return [self._member_to_entity(m) for m in models]

    async def add_member(self, member: TeamMember) -> TeamMember:
        model = self._member_to_model(member)
        self.session.add(model)
        await self.session.commit()
        await self.session.refresh(model)
        return self._member_to_entity(model)

    async def remove_member(self, team_id: str, agent_id: str) -> bool:
        result = await self.session.execute(
            select(TeamMemberModel).where(
                TeamMemberModel.team_id == team_id,
                TeamMemberModel.agent_id == agent_id,
            )
        )
        model = result.scalar_one_or_none()
        if not model:
            return False
        await self.session.delete(model)
        await self.session.commit()
        return True

    async def get_member(self, team_id: str, agent_id: str) -> Optional[TeamMember]:
        result = await self.session.execute(
            select(TeamMemberModel).where(
                TeamMemberModel.team_id == team_id,
                TeamMemberModel.agent_id == agent_id,
            )
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._member_to_entity(model)

    # ── Entity ↔ Model mapping ────────────────────────────

    def _team_to_entity(self, model: TeamModel) -> Team:
        return Team(
            id=model.id,
            name=model.name,
            description=model.description or "",
            leader_id=model.leader_id,
            goal=model.goal or "",
            status=TeamStatus(model.status) if model.status else TeamStatus.IDLE,
            config=model.config or {},
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _team_to_model(self, entity: Team) -> TeamModel:
        return TeamModel(
            id=entity.id,
            name=entity.name,
            description=entity.description,
            leader_id=entity.leader_id,
            goal=entity.goal,
            status=entity.status.value if isinstance(entity.status, TeamStatus) else entity.status,
            config=entity.config,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    def _member_to_entity(self, model: TeamMemberModel) -> TeamMember:
        return TeamMember(
            id=model.id,
            team_id=model.team_id,
            agent_id=model.agent_id,
            role=TeamRole(model.role) if model.role else TeamRole.MEMBER,
            status=model.status or "idle",
            joined_at=model.joined_at,
        )

    def _member_to_model(self, entity: TeamMember) -> TeamMemberModel:
        return TeamMemberModel(
            id=entity.id,
            team_id=entity.team_id,
            agent_id=entity.agent_id,
            role=entity.role.value if isinstance(entity.role, TeamRole) else entity.role,
            status=entity.status,
            joined_at=entity.joined_at,
        )
