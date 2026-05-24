"""基础设施层 - AgentRepository SQLite 实现"""

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.agent.agent import Agent, CONFIG_FILES
from src.domain.repositories.agent_repository import IAgentRepository
from src.infrastructure.database.models.agent_model import AgentModel


class SQLiteAgentRepository(IAgentRepository):
    """SQLite Agent 仓储实现"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, agent_id: str) -> Optional[Agent]:
        """根据 ID 获取 Agent"""
        result = await self.session.execute(select(AgentModel).where(AgentModel.id == agent_id))
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._to_entity(model)

    async def add(self, agent: Agent) -> Agent:
        """新增 Agent"""
        model = self._to_model(agent)
        self.session.add(model)
        await self.session.commit()
        await self.session.refresh(model)
        return self._to_entity(model)

    async def update(self, agent: Agent) -> Agent:
        """更新 Agent"""
        result = await self.session.execute(select(AgentModel).where(AgentModel.id == agent.id))
        model = result.scalar_one_or_none()
        if not model:
            raise ValueError(f"Agent {agent.id} not found")

        model.name = agent.name
        model.description = agent.description
        model.vibes = agent.vibes
        model.identity_md = agent.identity_md
        model.soul_md = agent.soul_md
        model.agents_md = agent.agents_md
        model.bootstrap_md = agent.bootstrap_md
        model.memory_md = agent.memory_md
        model.tools_md = agent.tools_md
        model.user_md = agent.user_md
        model.config_version = agent.config_version
        model.updated_at = agent.updated_at

        await self.session.commit()
        await self.session.refresh(model)
        return self._to_entity(model)

    async def remove(self, agent_id: str) -> bool:
        """删除 Agent"""
        result = await self.session.execute(select(AgentModel).where(AgentModel.id == agent_id))
        model = result.scalar_one_or_none()
        if not model:
            return False

        await self.session.delete(model)
        await self.session.commit()
        return True

    async def list_all(self, limit: int = 100, offset: int = 0) -> list[Agent]:
        """获取 Agent 列表"""
        result = await self.session.execute(
            select(AgentModel).order_by(AgentModel.created_at.desc()).limit(limit).offset(offset)
        )
        models = result.scalars().all()
        return [self._to_entity(m) for m in models]

    async def get_by_name(self, name: str) -> Optional[Agent]:
        """根据名称获取 Agent"""
        result = await self.session.execute(select(AgentModel).where(AgentModel.name == name))
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._to_entity(model)

    async def update_config(self, agent_id: str, config_fields: dict[str, str]) -> Optional[Agent]:
        """部分更新配置文件，自动递增版本号"""
        result = await self.session.execute(select(AgentModel).where(AgentModel.id == agent_id))
        model = result.scalar_one_or_none()
        if not model:
            return None

        for field_name, value in config_fields.items():
            if field_name in CONFIG_FILES and value is not None:
                setattr(model, field_name, value)

        model.config_version = (model.config_version or 0) + 1
        model.updated_at = datetime.now()

        await self.session.commit()
        await self.session.refresh(model)
        return self._to_entity(model)

    def _to_entity(self, model: AgentModel) -> Agent:
        """数据库模型转领域实体"""
        return Agent(
            id=model.id,
            name=model.name,
            description=model.description or "",
            vibes=model.vibes or "[]",
            identity_md=model.identity_md or "",
            soul_md=model.soul_md or "",
            agents_md=model.agents_md or "",
            bootstrap_md=model.bootstrap_md or "",
            memory_md=model.memory_md or "",
            tools_md=model.tools_md or "",
            user_md=model.user_md or "",
            config_version=model.config_version or 1,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_model(self, entity: Agent) -> AgentModel:
        """领域实体转数据库模型"""
        return AgentModel(
            id=entity.id,
            name=entity.name,
            description=entity.description,
            vibes=entity.vibes,
            identity_md=entity.identity_md,
            soul_md=entity.soul_md,
            agents_md=entity.agents_md,
            bootstrap_md=entity.bootstrap_md,
            memory_md=entity.memory_md,
            tools_md=entity.tools_md,
            user_md=entity.user_md,
            config_version=entity.config_version,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )
