"""领域层 - Skill 仓储接口"""

from abc import ABC, abstractmethod
from typing import Optional

from src.domain.entities.skill_def import SkillDef


class ISkillRepository(ABC):
    """Skill 仓储接口 - 定义持久化操作规范"""

    @abstractmethod
    async def add(self, skill: SkillDef) -> SkillDef:
        """新增 Skill"""
        pass

    @abstractmethod
    async def get_by_id(self, skill_id: str) -> Optional[SkillDef]:
        """根据 ID 获取 Skill"""
        pass

    @abstractmethod
    async def get_by_name(self, name: str) -> Optional[SkillDef]:
        """根据名称获取 Skill（唯一性校验）"""
        pass

    @abstractmethod
    async def list_all(
        self,
        limit: int = 100,
        offset: int = 0,
        category: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> tuple[list[SkillDef], int]:
        """获取 Skill 列表（分页 + 筛选），返回 (列表, 总数)"""
        pass

    @abstractmethod
    async def get_enabled(self) -> list[SkillDef]:
        """获取所有启用的 Skills（对话注入用）"""
        pass

    @abstractmethod
    async def get_by_ids(self, skill_ids: list[str]) -> list[SkillDef]:
        """根据 ID 列表批量获取 Skills（对话注入用）"""
        pass

    @abstractmethod
    async def update(self, skill: SkillDef) -> SkillDef:
        """更新 Skill"""
        pass

    @abstractmethod
    async def remove(self, skill_id: str) -> bool:
        """删除 Skill"""
        pass
