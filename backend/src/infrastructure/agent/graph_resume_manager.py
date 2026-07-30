"""图恢复管理器。

当 LangGraph 因人在回路确认而 interrupt() 暂停时，存储恢复所需的
上下文（graph + config）；/approvals 端点收到用户决策后取回并恢复执行。

进程级单例——同一进程内初始执行与恢复使用同一 MemorySaver 实例。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from langgraph.graph.state import CompiledStateGraph

logger = logging.getLogger(__name__)


@dataclass
class ResumeContext:
    """一次中断的恢复上下文。"""

    graph: CompiledStateGraph
    config: dict[str, Any]
    task_id: str
    session_id: str
    # 恢复后回调：finalize task、更新状态等
    on_complete: Any = None  # async callable(result)


class GraphResumeManager:
    """管理因 interrupt() 暂停的图执行，支持用户决策后恢复。"""

    def __init__(self) -> None:
        self._pending: dict[str, ResumeContext] = {}
        self._lock = asyncio.Lock()

    async def register(self, task_id: str, ctx: ResumeContext) -> None:
        """注册待恢复的图执行。

        同一个 task_id 重复注册会覆盖（前一次中断未恢复就再次中断的情况）。
        """
        async with self._lock:
            self._pending[task_id] = ctx
            logger.info(
                "GraphResumeManager: registered task_id=%s for resume", task_id
            )

    async def get(self, task_id: str) -> Optional[ResumeContext]:
        """获取恢复上下文（不移除，恢复完成后再 remove）。"""
        async with self._lock:
            return self._pending.get(task_id)

    async def remove(self, task_id: str) -> None:
        """移除恢复上下文（图执行完成或取消后调用）。"""
        async with self._lock:
            if self._pending.pop(task_id, None):
                logger.info(
                    "GraphResumeManager: removed task_id=%s", task_id
                )

    async def resume(self, task_id: str, decision: str) -> bool:
        """恢复暂停的图执行。

        以 Command(resume=decision) 重新调用 graph.ainvoke()，
        在后台 asyncio.Task 中运行直到完成或再次中断。

        Returns:
            True 如果找到并启动了恢复；False 如果没有待恢复的上下文。
        """
        from langgraph.types import Command

        ctx = await self.get(task_id)
        if ctx is None:
            logger.warning(
                "GraphResumeManager: no pending context for task_id=%s", task_id
            )
            return False

        async def _resume_loop():
            """在后台恢复图执行。若再次中断则重新注册，等待下次决策。"""
            from langgraph.errors import GraphInterrupt as GI

            current_config = ctx.config
            current_config["configurable"]["thread_id"] = task_id
            should_cleanup = True

            try:
                logger.info(
                    "GraphResumeManager: resuming task_id=%s with decision=%s",
                    task_id, decision,
                )
                result = await ctx.graph.ainvoke(
                    Command(resume=decision), current_config
                )

                logger.info(
                    "GraphResumeManager: task_id=%s completed, result keys=%s",
                    task_id, list(result.keys()) if result else "None",
                )

                if ctx.on_complete:
                    await ctx.on_complete(result)

            except GI:
                # 图再次中断（同一 agent loop 中另一个危险命令）
                logger.info(
                    "GraphResumeManager: task_id=%s interrupted again, "
                    "re-registering for next decision", task_id
                )
                ctx.config = current_config
                await self.register(task_id, ctx)
                should_cleanup = False  # 不清理，等待下次 /approvals

            except asyncio.CancelledError:
                logger.info("GraphResumeManager: task_id=%s resume cancelled", task_id)
            except Exception:
                logger.exception(
                    "GraphResumeManager: task_id=%s resume failed", task_id
                )
            finally:
                if should_cleanup:
                    await self.remove(task_id)

        asyncio.create_task(_resume_loop())
        return True


# ── 进程级共享单例 ─────────────────────────────────────────────

_default_resume_manager: Optional[GraphResumeManager] = None


def get_default_resume_manager() -> GraphResumeManager:
    global _default_resume_manager
    if _default_resume_manager is None:
        _default_resume_manager = GraphResumeManager()
    return _default_resume_manager
