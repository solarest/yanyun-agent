"""记忆子域 - 领域服务"""

import logging
from typing import Optional

from src.domain.memory.entity import MemoryCategory, MemoryEntry
from src.domain.memory.query import MemoryQuery, MemorySearchResult
from src.domain.memory.repository import IMemoryRepository
from src.domain.services.token_utils import count_tokens

logger = logging.getLogger(__name__)

# Prompt 注入时的最大 Token 预算（记忆摘要）
MEMORY_PROMPT_MAX_TOKENS = 800


class MemoryService:
    """记忆管理领域服务

    职责：
    - 记忆条目的验证
    - 重要性评分的计算与更新
    - 相似记忆的合并检测
    - 记忆格式化为 Prompt 注入文本
    """

    def __init__(self, repository: Optional[IMemoryRepository] = None):
        self._repo = repository

    def validate(self, entry: MemoryEntry) -> None:
        """验证记忆条目

        Args:
            entry: 待验证的记忆条目

        Raises:
            ValueError: 验证失败
        """
        if not entry.agent_id:
            raise ValueError("agent_id is required")
        if not entry.content or not entry.content.strip():
            raise ValueError("content is required")
        if len(entry.content) > 10000:
            raise ValueError("content exceeds 10000 characters")
        if not (0.0 <= entry.importance <= 1.0):
            raise ValueError("importance must be between 0.0 and 1.0")

    async def refresh_importance(
        self, entry: MemoryEntry
    ) -> MemoryEntry:
        """刷新记忆的重要性评分并持久化

        基于访问模式自动调整重要性评分。
        高访问频次 + 最近访问 → 高重要性。

        Args:
            entry: 要更新的记忆条目

        Returns:
            更新后的记忆条目
        """
        entry.importance = entry.compute_importance()
        if self._repo:
            await self._repo.update(entry)
        return entry

    def should_consolidate(
        self,
        existing: list[MemoryEntry],
        new_entry: MemoryEntry,
        similarity_threshold: float = 0.7,
    ) -> Optional[MemoryEntry]:
        """检测是否需要合并相似记忆

        简单策略：内容相似度检测（基于关键词重叠）。

        Args:
            existing: 已有记忆列表
            new_entry: 新记忆
            similarity_threshold: 相似度阈值

        Returns:
            应合并的已有记忆，不满足条件时返回 None
        """
        new_words = set(new_entry.content.lower().split())
        if len(new_words) < 3:
            return None

        best_match: Optional[MemoryEntry] = None
        best_score = 0.0

        for mem in existing:
            mem_words = set(mem.content.lower().split())
            if len(mem_words) < 3:
                continue
            intersection = new_words & mem_words
            union = new_words | mem_words
            if len(union) == 0:
                continue
            jaccard = len(intersection) / len(union)
            if jaccard > similarity_threshold and jaccard > best_score:
                best_score = jaccard
                best_match = mem

        return best_match if best_match else None

    def format_for_prompt(
        self,
        entries: list[MemoryEntry],
        max_tokens: int = MEMORY_PROMPT_MAX_TOKENS,
    ) -> str:
        """将记忆列表格式化为 Prompt 注入文本

        按重要性降序排列，在 Token 预算内尽可能多地包含记忆。
        用于 Layer 7 Memory System 注入。

        Args:
            entries: 记忆条目列表
            max_tokens: Token 预算上限

        Returns:
            可供注入 system prompt 的记忆格式化文本
        """
        if not entries:
            return ""

        # 按重要性降序排列
        sorted_entries = sorted(entries, key=lambda e: e.importance, reverse=True)

        lines: list[str] = []
        total_tokens = 0

        for entry in sorted_entries:
            # 格式化单条记忆：分类标签 + 内容 + 标签
            category_label = _category_label(entry.category)
            line = f"- [{category_label}] {entry.content}"
            if entry.tags:
                line += f"  # {' #'.join(entry.tags)}"

            line_tokens = count_tokens(line)
            if total_tokens + line_tokens > max_tokens:
                break

            lines.append(line)
            total_tokens += line_tokens

        if not lines:
            return ""

        header = "# Relevant Memories\n\n"
        body = "\n".join(lines)
        footer = (
            f"\n\n{len(lines)} memories loaded "
            f"(importance-weighted, top {len(lines)}/{len(entries)})"
        )

        return header + body + footer

    async def get_relevant_memories(
        self,
        agent_id: str,
        context: str = "",
        limit: int = 10,
    ) -> list[MemorySearchResult]:
        """获取与当前上下文相关的记忆

        优先使用语义搜索（如有 repo），降级为按重要性排序。

        Args:
            agent_id: Agent ID
            context: 当前对话上下文（用于相关性匹配）
            limit: 返回结果上限

        Returns:
            相关性排序的记忆搜索结果列表
        """
        if not self._repo:
            return []

        if context.strip():
            query = MemoryQuery(
                agent_id=agent_id,
                query=context[:200],
                limit=limit,
            )
            return await self._repo.search(query)

        entries = await self._repo.list_by_agent(agent_id, limit=limit)
        return [
            MemorySearchResult(entry=e, score=e.importance)
            for e in entries
        ]


def _category_label(category: MemoryCategory) -> str:
    """分类标签映射"""
    labels = {
        MemoryCategory.PREFERENCE: "偏好",
        MemoryCategory.FACT: "事实",
        MemoryCategory.DECISION: "决策",
        MemoryCategory.INSTRUCTION: "指令",
        MemoryCategory.KNOWLEDGE: "知识",
        MemoryCategory.GENERAL: "通用",
    }
    return labels.get(category, "通用")
