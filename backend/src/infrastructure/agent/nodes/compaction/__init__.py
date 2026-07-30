"""压缩策略模块 — 导出所有策略类和工厂函数"""

from src.infrastructure.agent.nodes.compaction.strategy import (
    CompactionResult,
    CompactionStrategy,
)
from src.infrastructure.agent.nodes.compaction.skip import SkipStrategy
from src.infrastructure.agent.nodes.compaction.soft_prune import SoftPruneStrategy
from src.infrastructure.agent.nodes.compaction.micro_compact import MicroCompactStrategy
from src.infrastructure.agent.nodes.compaction.emergency_compact import (
    EmergencyCompactStrategy,
)
from src.infrastructure.agent.nodes.compaction.summary_generator import SummaryGenerator
from src.infrastructure.agent.nodes.compaction.compact_utils import compact_messages


def _default_strategies() -> list[CompactionStrategy]:
    """返回按 priority 降序排列的默认策略链。

    ContextCompactNode 按此顺序遍历，第一个 should_apply()==True 的策略被执行。
    """
    return [
        EmergencyCompactStrategy(),
        MicroCompactStrategy(),
        SoftPruneStrategy(),
        SkipStrategy(),
    ]


__all__ = [
    "CompactionResult",
    "CompactionStrategy",
    "SkipStrategy",
    "SoftPruneStrategy",
    "MicroCompactStrategy",
    "EmergencyCompactStrategy",
    "SummaryGenerator",
    "compact_messages",
    "_default_strategies",
]
