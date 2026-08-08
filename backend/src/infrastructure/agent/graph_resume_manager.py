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

    async def resume(
        self, task_id: str, decision: str,
        file_storage=None, task_repo=None,
    ) -> bool:
        """恢复暂停的图执行。

        以 Command(resume=decision) 重新调用 graph.ainvoke()，
        在后台 asyncio.Task 中运行直到完成或再次中断。

        如果内存中无上下文（进程重启后），回退到 checkpoint 文件恢复。

        Returns:
            True 如果找到并启动了恢复；False 如果没有待恢复的上下文。
        """
        from langgraph.types import Command

        ctx = await self.get(task_id)
        if ctx is not None:
            return await self._resume_from_context(task_id, decision, ctx)

        # Fallback: checkpoint-based resume after process restart
        if file_storage is not None:
            return await self._resume_from_checkpoint(
                task_id, decision, file_storage, task_repo,
            )

        logger.warning(
            "GraphResumeManager: no pending context for task_id=%s", task_id
        )
        return False

    async def _resume_from_context(self, task_id: str, decision: str, ctx) -> bool:
        """Resume using in-memory ResumeContext."""
        from langgraph.types import Command
        from langgraph.errors import GraphInterrupt as GI

        async def _resume_loop():
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
                logger.info(
                    "GraphResumeManager: task_id=%s interrupted again, "
                    "re-registering for next decision", task_id
                )
                ctx.config = current_config
                await self.register(task_id, ctx)
                should_cleanup = False

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

    async def _resume_from_checkpoint(
        self, task_id: str, decision: str, file_storage, task_repo,
    ) -> bool:
        """Resume from checkpointer.json after process restart.

        Loads checkpointer state from file, rebuilds the graph with
        FileBackedSaver, and resumes with Command(resume=decision).
        """
        from datetime import datetime
        from langgraph.types import Command
        from src.infrastructure.agent.file_backed_saver import FileBackedSaver

        try:
            task = await task_repo.get_by_id(task_id) if task_repo else None
            if task is None:
                logger.warning("CheckpointResume: task %s not found", task_id)
                return False

            session_id = task.session_id
            task_dir = file_storage.base_path / session_id / task_id
            ckpt_file = task_dir / "checkpointer.json"

            if not ckpt_file.exists():
                logger.warning("CheckpointResume: no checkpointer.json for %s", task_id)
                return False

            saver = FileBackedSaver(file_path=str(ckpt_file))
            from src.infrastructure.agent.workflow_builder import AgentWorkflowBuilder
            graph = AgentWorkflowBuilder.build_with_checkpointer(saver)

            config = {
                "configurable": {
                    "thread_id": task_id,
                    "checkpoint_ns": "",
                }
            }

            async def _resume_loop():
                try:
                    result = await graph.ainvoke(
                        Command(resume=decision), config
                    )
                    logger.info(
                        "CheckpointResume: task_id=%s resumed successfully", task_id
                    )
                    # Update task status after successful resume
                    task.status = result.get("error") and "failed" or "completed"
                    task.completed_at = datetime.now()
                    task.result = result.get("final_result")
                    task.error = result.get("error")
                    await task_repo.update(task)
                except Exception:
                    logger.exception(
                        "CheckpointResume: task_id=%s resume failed", task_id
                    )
                    try:
                        task.status = "failed"
                        task.completed_at = datetime.now()
                        await task_repo.update(task)
                    except Exception:
                        pass

            asyncio.create_task(_resume_loop())
            return True

        except Exception:
            logger.exception("CheckpointResume: failed for task %s", task_id)
            return False


# ── 进程级共享单例 ─────────────────────────────────────────────

_default_resume_manager: Optional[GraphResumeManager] = None


def get_default_resume_manager() -> GraphResumeManager:
    global _default_resume_manager
    if _default_resume_manager is None:
        _default_resume_manager = GraphResumeManager()
    return _default_resume_manager
