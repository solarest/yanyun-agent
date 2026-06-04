"""记忆子域 - 查询定义"""

from dataclasses import dataclass, field
from typing import Optional

from src.domain.memory.entity import MemoryCategory, MemoryEntry


@dataclass
class MemoryQuery:
    """记忆查询参数

    Attributes:
        agent_id: 所属 Agent ID（必填）
        query: 搜索关键词（文本匹配）
        category: 按分类筛选
        tags: 按标签筛选
        min_importance: 最低重要性阈值
        limit: 返回结果上限
    """
    agent_id: str
    query: str = ""
    category: Optional[MemoryCategory] = None
    tags: list[str] = field(default_factory=list)
    min_importance: float = 0.0
    limit: int = 10


@dataclass
class MemorySearchResult:
    """记忆搜索结果

    Attributes:
        entry: 记忆条目
        score: 相关性评分 (0.0~1.0)
    """
    entry: MemoryEntry
    score: float = 0.0
