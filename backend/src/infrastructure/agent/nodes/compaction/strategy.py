"""压缩策略抽象基类与结果类型

定义可插拔压缩策略框架的核心接口。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.domain.aggregates.agent.agent_state import AgentState
    from langgraph.types import RunnableConfig
    from src.infrastructure.agent.nodes.base_node import NodeContext


@dataclass
class CompactionResult:
    """压缩策略的执行结果

    Attributes:
        strategy: 策略标识符 (e.g. "micro_compact")
        messages: 处理后的消息列表 (含 RemoveMessage)
        token_estimate: 压缩后的 Token 估算值
        removed_count: 移除的消息数量
        baseline_invalidated: Token baseline 是否失效
    """

    strategy: str
    messages: list[Any] = field(default_factory=list)
    token_estimate: int = 0
    removed_count: int = 0
    baseline_invalidated: bool = False
    pruned_count: int = 0
    """soft_prune 修剪的 ToolMessage 数量"""

    # 以下为 emergency_compact 特有额外字段
    compaction_attempts: int | None = None
    """紧急压缩次数递增后的值"""
    clear_emergency: bool = False
    """是否清零 emergency_compact_requested 标志"""

    def to_state_update(self) -> dict:
        """转换为 AgentState update 字典"""
        update: dict = {
            "messages": self.messages,
            "phase": "context_compacting",
            "context_token_estimate": self.token_estimate,
            "last_context_strategy": self.strategy,
        }
        if self.baseline_invalidated:
            update["context_token_baseline"] = None
            update["context_token_baseline_message_count"] = 0
        if self.compaction_attempts is not None:
            update["context_compaction_attempts"] = self.compaction_attempts
        if self.clear_emergency:
            update["emergency_compact_requested"] = False
        return update


class CompactionStrategy(ABC):
    """压缩策略抽象基类

    每个策略声明 priority，ContextCompactNode 按 priority 降序遍历，
    第一个 should_apply() 返回 True 的策略被执行。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """策略名称 (用于日志和 event)"""
        ...

    @property
    @abstractmethod
    def priority(self) -> int:
        """优先级 (越大越优先): Emergency=3 > Micro=2 > SoftPrune=1 > Skip=0"""
        ...

    @abstractmethod
    def should_apply(
        self,
        state: AgentState,
        messages: list,
        current_tokens: int,
        max_tokens: int,
    ) -> bool:
        """判断是否应该应用此策略"""
        ...

    @abstractmethod
    async def apply(
        self,
        state: AgentState,
        messages: list,
        current_tokens: int,
        max_tokens: int,
        config: RunnableConfig,
        context: NodeContext,
    ) -> CompactionResult:
        """执行压缩策略"""
        ...
