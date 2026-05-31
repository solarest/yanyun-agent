"""应用层 - 任务完成处理服务

处理 Agent Loop 终态结果：持久化消息、更新 Task 状态、发射 SSE 事件、发布领域事件。
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from src.domain.aggregates.session.session_message import (
    MessageStatus,
    SessionMessage,
    SessionMessageRole,
)
from src.domain.aggregates.task.task import Task, TaskStatus
from src.domain.entities.event_types import AgentEventType
from src.domain.events.task_events import TaskCompleted, TaskFailed
from src.domain.repositories.event_publisher import IEventPublisher
from src.domain.repositories.session_message_repository import (
    ISessionMessageRepository,
)
from src.domain.repositories.session_repository import ISessionRepository
from src.domain.repositories.task_repository import ITaskRepository
from src.domain.services import IEventEmitter
from src.domain.services.message_content import MessageContentService

logger = logging.getLogger(__name__)


class TaskCompletionService:
    """处理 Agent Loop 执行完毕后的终态结果。

    负责：
    1. 解析 LangGraph 执行结果（消息、工具调用/结果、thinking_text）
    2. 保存 assistant SessionMessage
    3. 更新 Task 状态（COMPLETED / FAILED）
    4. 更新 Session 元数据
    5. 发射 SSE 事件（phase_changed, session:message:saved, task:completed/failed）
    6. 发布领域事件（TaskCompleted / TaskFailed）
    """

    def __init__(
        self,
        message_repo: ISessionMessageRepository,
        task_repo: Optional[ITaskRepository] = None,
        session_repo: Optional[ISessionRepository] = None,
        event_publisher: Optional[IEventPublisher] = None,
    ):
        self.message_repo = message_repo
        self.task_repo = task_repo
        self.session_repo = session_repo
        self.event_publisher = event_publisher

    async def finalize(
        self,
        *,
        task: Task,
        session_id: str,
        result: Dict[str, Any],
        event_emitter: Optional[IEventEmitter] = None,
        persist_session_messages: bool = True,
    ) -> None:
        """处理终态结果。

        Args:
            task: Task 实体
            session_id: Session ID
            result: LangGraph 执行结果
            event_emitter: 事件发射器
            persist_session_messages: 是否持久化会话消息（sub-agent 模式为 False）
        """
        final_result = result.get("final_result")
        error = result.get("error")
        final_turn = result.get("current_turn", task.current_turn)
        previous_phase = result.get("phase", "thinking")

        all_tool_calls = []
        all_tool_results = []
        for msg in result.get("messages", []):
            tc = None
            if isinstance(msg, dict):
                tc = msg.get("tool_calls")
            elif hasattr(msg, "tool_calls"):
                tc = msg.tool_calls
            if tc:
                for t in tc:
                    if isinstance(t, dict):
                        all_tool_calls.append(
                            {"name": t.get("name", ""), "args": t.get(
                                "args", {}), "id": t.get("id", "")}
                        )
                    else:
                        all_tool_calls.append(
                            {
                                "name": getattr(t, "name", ""),
                                "args": getattr(t, "args", {}) or {},
                                "id": getattr(t, "id", ""),
                            }
                        )

        # 分离 clarify 输出与普通工具结果：
        # - clarify 的输出作为 assistant 正文呈现给用户，不进入 tool_results
        # - 其他工具正常收集到 all_tool_results
        clarify_outputs: list[str] = []
        for tool_call_id, tool_result in (result.get("tool_results") or {}).items():
            output = MessageContentService.extract_tool_output(tool_result)
            if tool_result.get("tool_name") == "clarify":
                if output:
                    clarify_outputs.append(output)
                continue
            all_tool_results.append(
                {
                    "tool_name": tool_result.get("tool_name", ""),
                    "id": tool_call_id,
                    "status": tool_result.get("status", "success"),
                    "result": output,
                }
            )

        # 计算 assistant 正文：
        # 1. 如果有 clarify 输出，直接使用 clarify 输出（final_result 已包含 clarify 内容，避免重复）
        # 2. 否则用终态输出 (final_result 或 error)
        # 3. 最后回溯取最后一条非空消息内容
        if clarify_outputs:
            assistant_content = "\n\n".join(clarify_outputs)
        else:
            assistant_content = (
                final_result
                or error
                or MessageContentService.extract_last_content(result.get("messages", []))
            )
        terminal_result = final_result or assistant_content

        thinking_text = result.get("thinking_text", "")

        assistant_msg: Optional[SessionMessage] = None
        if persist_session_messages:
            assistant_msg = SessionMessage(
                session_id=session_id,
                task_id=task.id,
                role=SessionMessageRole.ASSISTANT,
                content=assistant_content,
                thinking_content=thinking_text,
                has_thinking=bool(thinking_text),
                tool_calls=all_tool_calls,
                tool_results=all_tool_results,
                status=MessageStatus.ERROR if error else MessageStatus.COMPLETED,
                error=error,
            )
            assistant_msg = await self.message_repo.add(assistant_msg)

        if self.task_repo:
            task.status = TaskStatus.FAILED if error else TaskStatus.COMPLETED
            task.current_turn = final_turn
            task.completed_at = datetime.now()
            task.result = None if error else terminal_result
            task.error = error
            await self.task_repo.update(task)

        if persist_session_messages and self.session_repo:
            session = await self.session_repo.get_by_id(session_id)
            if session:
                session.update_metadata(assistant_content)
                await self.session_repo.update(session)

        if event_emitter:
            await event_emitter.emit_phase_changed(
                task.id,
                "failed" if error else "complete",
                previous_phase,
                final_turn,
            )
            if assistant_msg is not None:
                await event_emitter.emit(
                    task.id,
                    AgentEventType.SESSION_MESSAGE_SAVED,
                    self._build_message_event_payload(assistant_msg),
                )
            if error:
                await event_emitter.emit(task.id, AgentEventType.TASK_FAILED, {"error": error})
                if self.event_publisher:
                    await self.event_publisher.publish(TaskFailed(
                        task_id=task.id,
                        error=error,
                        failed_at=task.completed_at,
                    ))
            else:
                await event_emitter.emit(task.id, AgentEventType.TASK_COMPLETED, {"result": terminal_result})
                if self.event_publisher:
                    await self.event_publisher.publish(TaskCompleted(
                        task_id=task.id,
                        result=terminal_result or "",
                        completed_at=task.completed_at,
                    ))

    @staticmethod
    def _build_message_event_payload(message: SessionMessage) -> Dict[str, Any]:
        """构建 session:message:saved 事件载荷。"""
        return {
            "message": {
                "id": message.id,
                "session_id": message.session_id,
                "task_id": message.task_id,
                "role": message.role.value,
                "content": message.content,
                "thinking_content": message.thinking_content,
                "has_thinking": message.has_thinking,
                "tool_calls": message.tool_calls,
                "tool_results": message.tool_results,
                "status": message.status.value,
                "error": message.error,
                "cost": message.cost,
                "created_at": message.created_at.isoformat(),
            }
        }
