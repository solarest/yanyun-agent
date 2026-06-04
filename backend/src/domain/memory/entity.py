"""记忆子域 - MemoryEntry 实体"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from src.domain.entities.base import Entity


class MemoryCategory(str, Enum):
    """记忆分类"""
    PREFERENCE = "preference"      # 用户偏好
    FACT = "fact"                  # 事实信息
    DECISION = "decision"          # 决策记录
    INSTRUCTION = "instruction"    # 用户指令
    KNOWLEDGE = "knowledge"        # 领域知识
    GENERAL = "general"            # 通用


@dataclass
class MemoryEntry(Entity):
    """记忆条目实体

    表示一条持久化的记忆记录，支持跨会话存储和检索。

    Attributes:
        agent_id: 所属 Agent ID
        content: 记忆内容
        category: 记忆分类
        tags: 可搜索标签
        importance: 重要性权重 (0.0~1.0)
        source_session_id: 来源会话 ID
        access_count: 被检索次数
        last_accessed_at: 最近一次检索时间
        created_at: 创建时间
        updated_at: 更新时间
    """

    agent_id: str = ""
    content: str = ""
    category: MemoryCategory = MemoryCategory.GENERAL
    tags: list[str] = field(default_factory=list)
    importance: float = 0.5
    source_session_id: str = ""
    access_count: int = 0
    last_accessed_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None

    def record_access(self) -> None:
        """记录一次访问"""
        self.access_count += 1
        self.last_accessed_at = datetime.utcnow()

    def update_content(self, content: str) -> None:
        """更新记忆内容"""
        self.content = content
        self.updated_at = datetime.utcnow()

    def compute_importance(self) -> float:
        """根据访问模式计算重要性评分

        评分策略：
        - 基础分 0.3
        - 被访问过 +0.2
        - 访问次数加权 (最多 +0.3)
        - 最近访问加权 +0.2
        """
        score = 0.3
        if self.access_count > 0:
            score += 0.2
            score += min(self.access_count * 0.05, 0.3)
        if self.last_accessed_at:
            days_since = (datetime.utcnow() - self.last_accessed_at).days
            if days_since < 7:
                score += 0.2
        return min(score, 1.0)
