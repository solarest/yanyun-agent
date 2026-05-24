"""基础设施层 - SQLite Skill 仓储实现"""

import json
from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.skill.skill_def import SkillDef, SkillStep
from src.domain.repositories.skill_repository import ISkillRepository
from src.infrastructure.database.models.agent_model import SkillModel


class SQLiteSkillRepository(ISkillRepository):
    """SQLite Skill 仓储实现"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, skill: SkillDef) -> SkillDef:
        """新增 Skill"""
        if not skill.id:
            skill.id = str(uuid4())
        model = self._to_model(skill)
        self.session.add(model)
        await self.session.commit()
        await self.session.refresh(model)
        return self._to_entity(model)

    async def get_by_id(self, skill_id: str) -> Optional[SkillDef]:
        """根据 ID 获取 Skill"""
        result = await self.session.execute(
            select(SkillModel).where(SkillModel.id == skill_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._to_entity(model)

    async def get_by_name(self, name: str) -> Optional[SkillDef]:
        """根据名称获取 Skill"""
        result = await self.session.execute(
            select(SkillModel).where(SkillModel.name == name)
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._to_entity(model)

    async def list_all(
        self,
        limit: int = 100,
        offset: int = 0,
        category: Optional[str] = None,
        enabled: Optional[bool] = None,
    ) -> tuple[list[SkillDef], int]:
        """获取 Skill 列表（分页 + 筛选）"""
        query = select(SkillModel)
        count_query = select(func.count()).select_from(SkillModel)

        if category:
            query = query.where(SkillModel.category == category)
            count_query = count_query.where(SkillModel.category == category)

        if enabled is not None:
            enabled_val = 1 if enabled else 0
            query = query.where(SkillModel.enabled == enabled_val)
            count_query = count_query.where(SkillModel.enabled == enabled_val)

        # 总数
        total_result = await self.session.execute(count_query)
        total = total_result.scalar() or 0

        # 分页查询
        query = query.order_by(SkillModel.created_at.desc()
                               ).offset(offset).limit(limit)
        result = await self.session.execute(query)
        models = result.scalars().all()

        return [self._to_entity(m) for m in models], total

    async def get_enabled(self) -> list[SkillDef]:
        """获取所有启用的 Skills"""
        result = await self.session.execute(
            select(SkillModel)
            .where(SkillModel.enabled == 1)
            .order_by(SkillModel.created_at.desc())
        )
        models = result.scalars().all()
        return [self._to_entity(m) for m in models]

    async def get_by_ids(self, skill_ids: list[str]) -> list[SkillDef]:
        """根据 ID 列表批量获取 Skills"""
        if not skill_ids:
            return []
        result = await self.session.execute(
            select(SkillModel).where(SkillModel.id.in_(skill_ids))
        )
        models = result.scalars().all()
        return [self._to_entity(m) for m in models]

    async def update(self, skill: SkillDef) -> SkillDef:
        """更新 Skill"""
        result = await self.session.execute(
            select(SkillModel).where(SkillModel.id == skill.id)
        )
        model = result.scalar_one_or_none()
        if not model:
            raise ValueError(f"Skill {skill.id} not found")

        model.name = skill.name
        model.description = skill.description
        model.content = skill.content
        model.file_path = skill.file_path
        model.trigger_keywords = json.dumps(
            skill.trigger_keywords, ensure_ascii=False)
        model.steps = json.dumps(
            [{"name": s.name, "description": s.description, "tool_name": s.tool_name}
             for s in skill.steps],
            ensure_ascii=False,
        )
        model.category = skill.category
        model.enabled = 1 if skill.enabled else 0
        model.updated_at = skill.updated_at or datetime.now()

        await self.session.commit()
        await self.session.refresh(model)
        return self._to_entity(model)

    async def remove(self, skill_id: str) -> bool:
        """删除 Skill"""
        result = await self.session.execute(
            select(SkillModel).where(SkillModel.id == skill_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return False
        await self.session.delete(model)
        await self.session.commit()
        return True

    def _to_entity(self, model: SkillModel) -> SkillDef:
        """数据库模型 → 领域实体"""
        # 解析 JSON 字段
        try:
            trigger_keywords = json.loads(model.trigger_keywords or "[]")
        except (json.JSONDecodeError, TypeError):
            trigger_keywords = []

        try:
            steps_data = json.loads(model.steps or "[]")
        except (json.JSONDecodeError, TypeError):
            steps_data = []

        steps = [
            SkillStep(
                name=s.get("name", ""),
                description=s.get("description", ""),
                tool_name=s.get("tool_name"),
            )
            for s in steps_data
        ]

        return SkillDef(
            id=model.id,
            name=model.name,
            description=model.description or "",
            content=model.content or "",
            file_path=getattr(model, "file_path", "") or "",
            trigger_keywords=trigger_keywords,
            steps=steps,
            category=model.category or "general",
            enabled=bool(model.enabled),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_model(self, entity: SkillDef) -> SkillModel:
        """领域实体 → 数据库模型"""
        return SkillModel(
            id=entity.id,
            name=entity.name,
            description=entity.description,
            content=entity.content,
            file_path=entity.file_path,
            trigger_keywords=json.dumps(
                entity.trigger_keywords, ensure_ascii=False),
            steps=json.dumps(
                [{"name": s.name, "description": s.description, "tool_name": s.tool_name}
                 for s in entity.steps],
                ensure_ascii=False,
            ),
            category=entity.category,
            enabled=1 if entity.enabled else 0,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )
