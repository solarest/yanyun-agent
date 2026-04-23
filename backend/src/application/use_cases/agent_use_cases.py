"""应用层 - Agent 用例"""

from datetime import datetime
from typing import List

from src.domain.entities.agent import Agent, DEFAULT_SYSTEM_PROMPT_TEMPLATE
from src.domain.exceptions import AgentNotFoundError, DuplicateAgentNameError
from src.domain.repositories.agent_repository import IAgentRepository
from src.application.dtos.agent_dto import CreateAgentDTO, UpdateAgentDTO


class CreateAgentUseCase:
    """创建 Agent 用例

    校验名称唯一性，template 为 None 时使用默认模板，持久化实体。
    """

    def __init__(self, agent_repo: IAgentRepository) -> None:
        self.agent_repo = agent_repo

    async def execute(self, dto: CreateAgentDTO) -> Agent:
        """执行创建 Agent

        Args:
            dto: 创建 Agent 的请求数据

        Returns:
            创建的 Agent 实体

        Raises:
            DuplicateAgentNameError: 名称已存在时
        """
        existing = await self.agent_repo.get_by_name(dto.name)
        if existing is not None:
            raise DuplicateAgentNameError(f"Agent 名称 '{dto.name}' 已存在")

        template = (
            dto.system_prompt_template
            if dto.system_prompt_template is not None
            else DEFAULT_SYSTEM_PROMPT_TEMPLATE
        )

        agent = Agent(
            name=dto.name,
            role=dto.role,
            system_prompt_template=template,
            created_at=datetime.now(),
            updated_at=None,
        )
        return await self.agent_repo.add(agent)


class GetAgentUseCase:
    """获取单个 Agent 用例"""

    def __init__(self, agent_repo: IAgentRepository) -> None:
        self.agent_repo = agent_repo

    async def execute(self, agent_id: str) -> Agent:
        """根据 ID 获取 Agent

        Args:
            agent_id: Agent ID

        Returns:
            Agent 实体

        Raises:
            AgentNotFoundError: Agent 不存在时
        """
        agent = await self.agent_repo.get_by_id(agent_id)
        if agent is None:
            raise AgentNotFoundError(f"Agent '{agent_id}' 不存在")
        return agent


class ListAgentsUseCase:
    """获取 Agent 列表用例"""

    def __init__(self, agent_repo: IAgentRepository) -> None:
        self.agent_repo = agent_repo

    async def execute(self, limit: int = 100, offset: int = 0) -> List[Agent]:
        """获取分页 Agent 列表

        Args:
            limit: 每页数量
            offset: 偏移量

        Returns:
            Agent 列表
        """
        return await self.agent_repo.list_all(limit=limit, offset=offset)


class UpdateAgentUseCase:
    """更新 Agent 用例"""

    def __init__(self, agent_repo: IAgentRepository) -> None:
        self.agent_repo = agent_repo

    async def execute(self, agent_id: str, dto: UpdateAgentDTO) -> Agent:
        """部分更新 Agent

        Args:
            agent_id: Agent ID
            dto: 更新数据（PATCH 语义）

        Returns:
            更新后的 Agent 实体

        Raises:
            AgentNotFoundError: Agent 不存在时
            DuplicateAgentNameError: 新名称已被占用时
        """
        agent = await self.agent_repo.get_by_id(agent_id)
        if agent is None:
            raise AgentNotFoundError(f"Agent '{agent_id}' 不存在")

        if dto.name is not None and dto.name != agent.name:
            existing = await self.agent_repo.get_by_name(dto.name)
            if existing is not None:
                raise DuplicateAgentNameError(f"Agent 名称 '{dto.name}' 已存在")
            agent.name = dto.name

        if dto.role is not None:
            agent.role = dto.role

        if dto.system_prompt_template is not None:
            agent.system_prompt_template = dto.system_prompt_template

        agent.updated_at = datetime.now()
        return await self.agent_repo.update(agent)


class DeleteAgentUseCase:
    """删除 Agent 用例"""

    def __init__(self, agent_repo: IAgentRepository) -> None:
        self.agent_repo = agent_repo

    async def execute(self, agent_id: str) -> bool:
        """删除 Agent

        Args:
            agent_id: Agent ID

        Returns:
            是否删除成功

        Raises:
            AgentNotFoundError: Agent 不存在时
        """
        agent = await self.agent_repo.get_by_id(agent_id)
        if agent is None:
            raise AgentNotFoundError(f"Agent '{agent_id}' 不存在")
        return await self.agent_repo.remove(agent_id)
