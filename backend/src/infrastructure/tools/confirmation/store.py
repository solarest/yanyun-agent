"""待审批注册表与会话许可存储（task 3.1 / 3.2）。

二者均为进程级单例：经 `presentation/dependencies.py` 的访问器获取，
顶层 / sub-agent / team 的 `ConfirmationMiddleware` 与 `/approvals` 端点
共享同一实例——见 design 决策 θ。

非阻塞版：注册表仅追踪"哪些 (task_id, tool_call_id) 处于待确认状态"，
不再持有 Future——暂停/恢复由 LangGraph interrupt() / Command(resume=...)
机制处理。
"""

from __future__ import annotations

import asyncio
from typing import Optional


class PendingApprovalRegistry:
    """以 `(task_id, tool_call_id)` 为键的待审批调用注册表。

    仅追踪存在性（供 /approvals 端点校验），不再持有 Future。
    `task_id` 由调用方传入"有效 task_id"（sub-agent / team 取父 task_id）。
    """

    def __init__(self) -> None:
        self._futures: dict[tuple[str, str], None] = {}  # key → None 标记
        self._lock = asyncio.Lock()

    async def register(self, task_id: str, tool_call_id: str) -> None:
        """登记一个待确认调用（非阻塞——不再创建 Future）。"""
        async with self._lock:
            self._futures[(task_id, tool_call_id)] = None  # None 标记"已登记"

    async def has(self, task_id: str, tool_call_id: str) -> bool:
        """检查是否存在待确认调用。"""
        async with self._lock:
            return (task_id, tool_call_id) in self._futures

    async def remove(self, task_id: str, tool_call_id: str) -> None:
        """移除待确认调用登记。"""
        async with self._lock:
            self._futures.pop((task_id, tool_call_id), None)

    async def remove_task(self, task_id: str) -> None:
        """移除任务的全部待确认调用（任务取消时使用）。"""
        async with self._lock:
            for key in [key for key in self._futures if key[0] == task_id]:
                self._futures.pop(key, None)


class SessionApprovalStore:
    """会话级 allow-all 白名单：`{session_id: set[category]}`。

    同会话内（含其 sub-agent / team member）allow-all 不再追问；
    重启 / 新会话重新把关（仅内存）。
    """

    def __init__(self) -> None:
        self._allowed: dict[str, set[str]] = {}
        self._lock = asyncio.Lock()

    async def is_allowed(self, session_id: str, category: str) -> bool:
        async with self._lock:
            return category in self._allowed.get(session_id, set())

    async def allow(self, session_id: str, category: str) -> None:
        async with self._lock:
            self._allowed.setdefault(session_id, set()).add(category)


# ── 进程级共享单例 ─────────────────────────────────────────────
# 供管道工厂 build_default_pipeline 与 /approvals 端点共享同一实例——
# 否则端点解析不到 sub-agent/team 挂起的 Future（见 design 决策 θ）。

_default_registry: Optional[PendingApprovalRegistry] = None
_default_session_store: Optional[SessionApprovalStore] = None


def get_default_registry() -> PendingApprovalRegistry:
    global _default_registry
    if _default_registry is None:
        _default_registry = PendingApprovalRegistry()
    return _default_registry


def get_default_session_store() -> SessionApprovalStore:
    global _default_session_store
    if _default_session_store is None:
        _default_session_store = SessionApprovalStore()
    return _default_session_store
