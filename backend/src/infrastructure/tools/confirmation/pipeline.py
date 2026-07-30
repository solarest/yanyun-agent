"""默认工具执行管道工厂（task 6.1）。

构建含确认闸门的完整中间件管道，供顶层 `create_tool_registry` 与
sub-agent/team 的 `_build_tool_registry` 共用——确保所有执行路径共享同一组
中间件与（共享单例）审批存储。见 design 决策 ζ / θ。

顺序：Confirmation → Security → RateLimit → Timeout → Sandbox → final_handler。
Confirmation 须在 Security 之前（即 Timeout 之外），否则 30s 执行超时会
kill 掉等待审批的闸门。
"""

from __future__ import annotations

from typing import Optional

from src.infrastructure.tools.confirmation.classifier import CommandClassifier
from src.infrastructure.tools.confirmation.config import load_dangerous_commands
from src.infrastructure.tools.confirmation.store import (
    PendingApprovalRegistry,
    SessionApprovalStore,
    get_default_registry,
    get_default_session_store,
)
from src.infrastructure.tools.register.middleware.confirmation import (
    ConfirmationMiddleware,
)
from src.infrastructure.tools.register.middleware.rate_limit import RateLimitMiddleware
from src.infrastructure.tools.register.middleware.sandbox import SandboxMiddleware
from src.infrastructure.tools.register.middleware.security import SecurityMiddleware
from src.infrastructure.tools.register.middleware.timeout import TimeoutMiddleware
from src.infrastructure.tools.register.pipeline import ExecutionPipeline


def build_default_pipeline(
    registry: Optional[PendingApprovalRegistry] = None,
    session_store: Optional[SessionApprovalStore] = None,
) -> ExecutionPipeline:
    """构建默认工具执行管道。

    Args:
        registry: 待审批注册表；为 None 时用进程级共享单例（端点亦取此单例）。
        session_store: 会话许可存储；同上。
    """
    reg = registry if registry is not None else get_default_registry()
    store = session_store if session_store is not None else get_default_session_store()
    classifier = CommandClassifier(load_dangerous_commands())

    pipeline = ExecutionPipeline()
    pipeline.add_middleware(ConfirmationMiddleware(classifier, reg, store))
    pipeline.add_middleware(SecurityMiddleware(allowed_tools=None))
    pipeline.add_middleware(RateLimitMiddleware(global_max_per_minute=300))
    pipeline.add_middleware(TimeoutMiddleware())
    pipeline.add_middleware(SandboxMiddleware())
    return pipeline
