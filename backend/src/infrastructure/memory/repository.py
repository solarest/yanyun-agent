"""基础设施层 - SQLite Memory 仓储实现"""

import json
from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.memory.entity import MemoryCategory, MemoryEntry
from src.domain.memory.query import MemoryQuery, MemorySearchResult
from src.domain.memory.repository import IMemoryRepository
from src.infrastructure.database.models.agent_model import MemoryModel


class SQLiteMemoryRepository(IMemoryRepository):
    """SQLite 记忆仓储实现"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, entry: MemoryEntry) -> MemoryEntry:
        """新增记忆"""
        if not entry.id:
            entry.id = str(uuid4())
        model = self._to_model(entry)
        self.session.add(model)
        await self.session.commit()
        await self.session.refresh(model)
        return self._to_entity(model)

    async def get_by_id(self, memory_id: str) -> Optional[MemoryEntry]:
        """根据 ID 获取记忆"""
        result = await self.session.execute(
            select(MemoryModel).where(MemoryModel.id == memory_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._to_entity(model)

    async def search(self, query: MemoryQuery) -> list[MemorySearchResult]:
        """搜索记忆（文本匹配 + 分类/标签/重要性筛选）"""
        conditions = [MemoryModel.agent_id == query.agent_id]

        # 文本匹配
        if query.query.strip():
            search_term = f"%{query.query.strip()}%"
            conditions.append(
                or_(
                    MemoryModel.content.like(search_term),
                    MemoryModel.tags.like(search_term),
                )
            )

        # 分类筛选
        if query.category:
            conditions.append(MemoryModel.category == query.category.value)

        # 重要性阈值
        if query.min_importance > 0:
            importance_int = int(query.min_importance * 100)
            conditions.append(MemoryModel.importance >= importance_int)

        stmt = (
            select(MemoryModel)
            .where(*conditions)
            .order_by(MemoryModel.importance.desc(), MemoryModel.created_at.desc())
            .limit(query.limit)
        )
        result = await self.session.execute(stmt)
        models = result.scalars().all()

        results: list[MemorySearchResult] = []
        for model in models:
            entry = self._to_entity(model)
            score = 0.0
            if query.query.strip():
                query_lower = query.query.strip().lower()
                content_lower = entry.content.lower()
                if query_lower in content_lower:
                    score = 0.5 + (0.3 * entry.importance)
                else:
                    q_words = set(query_lower.split())
                    c_words = set(content_lower.split())
                    if q_words and c_words:
                        score = len(q_words & c_words) / len(q_words) * 0.5
            else:
                score = entry.importance
            results.append(MemorySearchResult(entry=entry, score=min(score, 1.0)))

        results.sort(key=lambda r: r.score, reverse=True)
        return results

    async def list_by_agent(
        self,
        agent_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MemoryEntry]:
        """列出 Agent 的所有记忆"""
        result = await self.session.execute(
            select(MemoryModel)
            .where(MemoryModel.agent_id == agent_id)
            .order_by(MemoryModel.importance.desc(), MemoryModel.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        models = result.scalars().all()
        return [self._to_entity(m) for m in models]

    async def update(self, entry: MemoryEntry) -> MemoryEntry:
        """更新记忆"""
        result = await self.session.execute(
            select(MemoryModel).where(MemoryModel.id == entry.id)
        )
        model = result.scalar_one_or_none()
        if not model:
            raise ValueError(f"Memory {entry.id} not found")

        model.content = entry.content
        model.category = entry.category.value
        model.tags = json.dumps(entry.tags, ensure_ascii=False)
        model.importance = int(entry.importance * 100)
        model.source_session_id = entry.source_session_id
        model.access_count = entry.access_count
        model.last_accessed_at = entry.last_accessed_at
        model.updated_at = entry.updated_at or datetime.utcnow()

        await self.session.commit()
        await self.session.refresh(model)
        return self._to_entity(model)

    async def remove(self, memory_id: str) -> bool:
        """删除记忆"""
        result = await self.session.execute(
            select(MemoryModel).where(MemoryModel.id == memory_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return False
        await self.session.delete(model)
        await self.session.commit()
        return True

    async def remove_by_agent(self, agent_id: str) -> int:
        """删除 Agent 的所有记忆"""
        result = await self.session.execute(
            delete(MemoryModel).where(MemoryModel.agent_id == agent_id)
        )
        await self.session.commit()
        return result.rowcount or 0

    async def count_by_agent(self, agent_id: str) -> int:
        """统计 Agent 的记忆数量"""
        result = await self.session.execute(
            select(func.count()).where(MemoryModel.agent_id == agent_id)
        )
        count = result.scalar() or 0
        return int(count)

    def _to_entity(self, model: MemoryModel) -> MemoryEntry:
        """数据库模型 → 领域实体"""
        try:
            tags = json.loads(model.tags or "[]")
        except (json.JSONDecodeError, TypeError):
            tags = []

        try:
            category = MemoryCategory(model.category)
        except ValueError:
            category = MemoryCategory.GENERAL

        return MemoryEntry(
            id=model.id,
            agent_id=model.agent_id,
            content=model.content or "",
            category=category,
            tags=tags,
            importance=model.importance / 100.0,
            source_session_id=model.source_session_id or "",
            access_count=model.access_count or 0,
            last_accessed_at=model.last_accessed_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_model(self, entity: MemoryEntry) -> MemoryModel:
        """领域实体 → 数据库模型"""
        return MemoryModel(
            id=entity.id,
            agent_id=entity.agent_id,
            content=entity.content,
            category=entity.category.value,
            tags=json.dumps(entity.tags, ensure_ascii=False),
            importance=int(entity.importance * 100),
            source_session_id=entity.source_session_id,
            access_count=entity.access_count,
            last_accessed_at=entity.last_accessed_at,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )
