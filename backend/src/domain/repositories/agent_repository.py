"""领域层 - Agent Repository 接口"""

from abc import ABC, abstractmethod
from typing import List, Optional

from src.domain.entities.agent import Agent


class IAgentRepository(ABC):
    """Agent 仓储接口

    定义 Agent 实体的持久化操作规范。
    """

    @abstractmethod
    async def get_by_id(self, agent_id: str) -> Optional[Agent]:
        """根据 ID 获取 Agent"""
        pass

    @abstractmethod
    async def add(self, agent: Agent) -> Agent:
        """新增 Agent"""
        pass

    @abstractmethod
    async def update(self, agent: Agent) -> Agent:
        """更新 Agent"""
        pass

    @abstractmethod
    async def remove(self, agent_id: str) -> bool:
        """删除 Agent"""
        pass

    @abstractmethod
    async def list_all(self, limit: int = 100, offset: int = 0) -> List[Agent]:
        """获取 Agent 列表"""
        pass

    @abstractmethod
    async def get_by_name(self, name: str) -> Optional[Agent]:
        """根据名称获取 Agent（用于唯一性校验）"""
        pass
