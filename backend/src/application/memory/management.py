"""应用层 - Memory 管理用例"""

import logging
from typing import Optional

from src.domain.memory.entity import MemoryCategory, MemoryEntry
from src.domain.memory.query import MemoryQuery, MemorySearchResult
from src.domain.memory.repository import IMemoryRepository
from src.domain.memory.service import MemoryService

logger = logging.getLogger(__name__)


class MemoryManagementUseCase:
    """记忆管理用例

    编排记忆的 CRUD 和搜索操作，注入领域服务进行验证和处理。
    """

    def __init__(
        self,
        memory_repo: IMemoryRepository,
        memory_service: Optional[MemoryService] = None,
    ):
        self._repo = memory_repo
        self._service = memory_service or MemoryService()

    async def add_memory(
        self,
        agent_id: str,
        content: str,
        category: str = "general",
        tags: Optional[list[str]] = None,
        importance: float = 0.5,
        source_session_id: str = "",
    ) -> MemoryEntry:
        """新增记忆"""
        try:
            cat = MemoryCategory(category)
        except ValueError:
            cat = MemoryCategory.GENERAL

        entry = MemoryEntry(
            agent_id=agent_id,
            content=content.strip(),
            category=cat,
            tags=tags or [],
            importance=importance,
            source_session_id=source_session_id,
        )

        # 领域验证
        self._service.validate(entry)

        # 检测是否需要合并相似记忆
        existing = await self._repo.list_by_agent(agent_id, limit=50)
        duplicate = self._service.should_consolidate(existing, entry)
        if duplicate:
            logger.info(
                "Consolidating memory to existing entry %s (similarity match)",
                duplicate.id,
            )
            duplicate.update_content(
                f"{duplicate.content}\n\n[Updated] {entry.content}"
            )
            return await self._repo.update(duplicate)

        return await self._repo.add(entry)

    async def search_memories(
        self,
        agent_id: str,
        query: str = "",
        category: Optional[str] = None,
        tags: Optional[list[str]] = None,
        min_importance: float = 0.0,
        limit: int = 10,
    ) -> list[MemorySearchResult]:
        """搜索记忆"""
        try:
            cat = MemoryCategory(category) if category else None
        except ValueError:
            cat = None

        memory_query = MemoryQuery(
            agent_id=agent_id,
            query=query.strip(),
            category=cat,
            tags=tags or [],
            min_importance=min_importance,
            limit=limit,
        )

        results = await self._repo.search(memory_query)

        # 记录访问
        for r in results:
            r.entry.record_access()
            await self._repo.update(r.entry)

        return results

    async def list_memories(
        self,
        agent_id: str,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[MemoryEntry], int]:
        """列出 Agent 的记忆（分页）"""
        offset = (page - 1) * page_size
        entries = await self._repo.list_by_agent(
            agent_id, limit=page_size, offset=offset
        )
        total = await self._repo.count_by_agent(agent_id)
        return entries, total

    async def get_memory(self, memory_id: str) -> Optional[MemoryEntry]:
        """获取单条记忆"""
        entry = await self._repo.get_by_id(memory_id)
        if entry:
            entry.record_access()
            await self._repo.update(entry)
        return entry

    async def update_memory(
        self,
        memory_id: str,
        content: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[list[str]] = None,
        importance: Optional[float] = None,
    ) -> Optional[MemoryEntry]:
        """更新记忆"""
        entry = await self._repo.get_by_id(memory_id)
        if not entry:
            return None

        if content is not None:
            entry.content = content.strip()
        if category is not None:
            try:
                entry.category = MemoryCategory(category)
            except ValueError:
                pass
        if tags is not None:
            entry.tags = tags
        if importance is not None:
            entry.importance = importance

        self._service.validate(entry)
        return await self._repo.update(entry)

    async def delete_memory(self, memory_id: str) -> bool:
        """删除记忆"""
        return await self._repo.remove(memory_id)

    async def get_relevant_for_session(
        self,
        agent_id: str,
        session_content: str = "",
        limit: int = 10,
    ) -> str:
        """获取与会话上下文相关的记忆（格式化为 Prompt 文本）"""
        results = await self._service.get_relevant_memories(
            agent_id=agent_id,
            context=session_content,
            limit=limit,
        )
        entries = [r.entry for r in results]
        return self._service.format_for_prompt(entries)
