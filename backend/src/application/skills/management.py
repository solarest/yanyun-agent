"""应用层 - Skill 管理用例

编排 Skill 查询与启用/禁用操作。
"""

from typing import Optional

from src.domain.skills import ISkillRepository, SkillDef


class SkillManagementUseCase:
    """Skill 管理用例

    职责：
    - 列表查询（分页 + 分类/启用状态筛选）
    - 获取启用的 Skills
    - 按 ID 获取单个 Skill
    - 切换 Skill 启用/禁用状态
    """

    def __init__(self, skill_repo: ISkillRepository) -> None:
        self._repo = skill_repo

    async def list_all(
        self,
        page: int = 1,
        page_size: int = 20,
        category: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> tuple[list[SkillDef], int]:
        """获取 Skill 列表（分页 + 筛选）

        Returns:
            (skills, total)
        """
        offset = (page - 1) * page_size
        return await self._repo.list_all(
            limit=page_size,
            offset=offset,
            category=category,
            enabled=enabled,
        )

    async def list_enabled(self) -> list[SkillDef]:
        """获取所有启用的 Skills（对话选择用）"""
        return await self._repo.get_enabled()

    async def get_by_id(self, skill_id: str) -> Optional[SkillDef]:
        """按 ID 获取 Skill"""
        return await self._repo.get_by_id(skill_id)

    async def toggle_enabled(self, skill_id: str) -> SkillDef:
        """切换 Skill 启用/禁用状态

        Args:
            skill_id: Skill ID

        Returns:
            更新后的 SkillDef

        Raises:
            SkillNotFoundError: Skill 不存在
        """
        skill = await self._repo.get_by_id(skill_id)
        if skill is None:
            raise SkillNotFoundError(skill_id)

        skill.toggle_enabled()
        return await self._repo.update(skill)


# ── 业务异常 ──────────────────────────────────────────────


class SkillNotFoundError(Exception):
    """Skill 不存在"""

    def __init__(self, skill_id: str) -> None:
        self.skill_id = skill_id
        super().__init__(f"Skill '{skill_id}' not found")
