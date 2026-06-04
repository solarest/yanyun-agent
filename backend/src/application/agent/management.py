"""应用层 - Agent 配置管理用例

编排 Agent CRUD 操作：名称唯一性校验、字段更新、版本递增。
"""

from datetime import datetime
from typing import Optional

from src.domain.agent.entity import Agent
from src.domain.agent.repository import IAgentRepository


class AgentManagementUseCase:
    """Agent 配置管理用例

    职责：
    - 创建 Agent（含名称唯一性校验）
    - 查询 Agent（列表/详情/配置）
    - 更新 Agent（含名称冲突检查 + 配置版本递增）
    - 删除 Agent
    """

    def __init__(self, agent_repo: IAgentRepository) -> None:
        self._repo = agent_repo

    async def create(
        self,
        name: str,
        description: str = "",
        vibes: Optional[list[str]] = None,
        identity_md: str = "",
        soul_md: str = "",
        agents_md: str = "",
        bootstrap_md: str = "",
        memory_md: str = "",
        tools_md: str = "",
        user_md: str = "",
    ) -> Agent:
        """创建 Agent，校验名称唯一性"""
        existing = await self._repo.get_by_name(name)
        if existing is not None:
            raise DuplicateAgentNameError(name)

        agent = Agent(
            name=name,
            description=description,
            identity_md=identity_md,
            soul_md=soul_md,
            agents_md=agents_md,
            bootstrap_md=bootstrap_md,
            memory_md=memory_md,
            tools_md=tools_md,
            user_md=user_md,
            created_at=datetime.now(),
            updated_at=None,
        )
        if vibes:
            agent.set_vibes(vibes)
        return await self._repo.add(agent)

    async def get_by_id(self, agent_id: str) -> Optional[Agent]:
        """按 ID 获取 Agent"""
        return await self._repo.get_by_id(agent_id)

    async def list_all(self, page: int = 1, page_size: int = 20) -> list[Agent]:
        """分页获取 Agent 列表"""
        offset = (page - 1) * page_size
        return await self._repo.list_all(limit=page_size, offset=offset)

    async def update(
        self,
        agent_id: str,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        vibes: Optional[list[str]] = None,
        identity_md: Optional[str] = None,
        soul_md: Optional[str] = None,
        agents_md: Optional[str] = None,
        bootstrap_md: Optional[str] = None,
        memory_md: Optional[str] = None,
        tools_md: Optional[str] = None,
        user_md: Optional[str] = None,
    ) -> Agent:
        """更新 Agent（PATCH 语义），校验名称冲突"""
        agent = await self._repo.get_by_id(agent_id)
        if agent is None:
            raise AgentNotFoundError(agent_id)

        if name is not None and name != agent.name:
            existing = await self._repo.get_by_name(name)
            if existing is not None:
                raise DuplicateAgentNameError(name)
            agent.name = name

        if description is not None:
            agent.description = description
        if vibes is not None:
            agent.set_vibes(vibes)

        # 配置文件字段（会触发版本递增）
        config_fields = {}
        for field_name in [
            "identity_md", "soul_md", "agents_md",
            "bootstrap_md", "memory_md", "tools_md", "user_md",
        ]:
            value = locals().get(field_name)
            if value is not None:
                config_fields[field_name] = value

        if config_fields:
            agent.update_config(**config_fields)
        else:
            agent.updated_at = datetime.now()

        return await self._repo.update(agent)

    async def update_config(
        self,
        agent_id: str,
        config_fields: dict[str, str],
    ) -> Agent:
        """部分更新配置文件，自动递增版本号"""
        agent = await self._repo.update_config(agent_id, config_fields)
        if agent is None:
            raise AgentNotFoundError(agent_id)
        return agent

    async def delete(self, agent_id: str) -> None:
        """删除 Agent"""
        agent = await self._repo.get_by_id(agent_id)
        if agent is None:
            raise AgentNotFoundError(agent_id)
        await self._repo.remove(agent_id)


# ── 业务异常 ──────────────────────────────────────────────


class AgentNotFoundError(Exception):
    """Agent 不存在"""

    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        super().__init__(f"Agent '{agent_id}' not found")


class DuplicateAgentNameError(Exception):
    """Agent 名称重复"""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"Agent name '{name}' already exists")
