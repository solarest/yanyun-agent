"""应用层 - SendMessage 用例

核心编排用例：用户发送消息 → 创建 Task → 异步启动 Agent Loop。
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from langchain_core.messages import AIMessage, HumanMessage

from src.application.use_cases.agent_workflow import AgentWorkflowBuilder
from src.application.use_cases.stream_event import StreamEventService
from src.domain.entities.session_message import (
    MessageStatus,
    SessionMessage,
    SessionMessageRole,
)
from src.domain.entities.task import Task, TaskConfig, TaskStatus
from src.domain.repositories.agent_repository import IAgentRepository
from src.domain.repositories.session_message_repository import (
    ISessionMessageRepository,
)
from src.domain.repositories.session_repository import ISessionRepository
from src.domain.repositories.task_repository import ITaskRepository
from src.domain.services.prompt_builder import PromptBuilder
from src.infrastructure.llm.model_factory import create_chat_model
from src.infrastructure.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


def _tool_defs_to_openai_functions(tool_registry: ToolRegistry) -> list:
    """将 ToolDef 列表转换为 OpenAI function schema 格式（供 bind_tools 使用）"""
    tool_defs = tool_registry.get_tool_defs()
    schemas = []
    for td in tool_defs:
        properties = {}
        required = []
        for p in td.parameters:
            prop: Dict[str, Any] = {
                "type": p.type,
                "description": p.description,
            }
            if p.enum:
                prop["enum"] = p.enum
            properties[p.name] = prop
            if p.required:
                required.append(p.name)

        schemas.append(
            {
                "type": "function",
                "function": {
                    "name": td.name,
                    "description": td.description,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    },
                },
            }
        )
    return schemas


class SendMessageUseCase:
    """发送消息用例 — 编排 Session 操作 + Agent Loop 启动"""

    def __init__(
        self,
        agent_repo: IAgentRepository,
        session_repo: ISessionRepository,
        message_repo: ISessionMessageRepository,
        task_repo: Optional[ITaskRepository] = None,
        event_service: Optional[StreamEventService] = None,
        tool_registry: Optional[ToolRegistry] = None,
    ):
        self.agent_repo = agent_repo
        self.session_repo = session_repo
        self.message_repo = message_repo
        self.task_repo = task_repo
        self.event_service = event_service
        self.tool_registry = tool_registry

    async def execute(
        self,
        agent_id: str,
        session_id: str,
        content: str,
        model: Optional[str] = None,
        max_turns: int = 100,
        workspace: str = "/tmp/agent-workspace",
    ) -> Dict[str, Any]:
        """执行发送消息流程

        同步部分（HTTP 请求内完成，返回 202）:
        1. 保存 user SessionMessage
        2. 更新 Session 元数据
        3. 创建 Task
        4. asyncio.create_task 启动后台 runner
        5. 返回 taskId + userMessage

        Args:
            agent_id: Agent ID
            session_id: Session ID
            content: 消息内容
            model: LLM 模型名称
            max_turns: 最大轮次
            workspace: 工作目录

        Returns:
            {"user_message": SessionMessage, "task_id": str}
        """
        # 1. 保存用户消息
        user_msg = SessionMessage(
            session_id=session_id,
            role=SessionMessageRole.USER,
            content=content,
            status=MessageStatus.COMPLETED,
        )
        user_msg = await self.message_repo.add(user_msg)

        # 2. 更新 Session 元数据
        session = await self.session_repo.get_by_id(session_id)
        if session:
            session.update_metadata(content)
            # 首条消息自动生成标题
            if session.message_count == 1:
                session.auto_title(content)
            await self.session_repo.update(session)

        # 3. 创建 Task
        from src.infrastructure.llm.config import LLMSettings

        effective_model = model or LLMSettings().default_model
        task = Task(
            message=content,
            workspace=workspace,
            status=TaskStatus.RUNNING,
            model=effective_model,
            config=TaskConfig(max_turns=max_turns),
            max_turns=max_turns,
            agent_id=agent_id,
            session_id=session_id,
            started_at=datetime.now(),
        )
        if self.task_repo:
            task = await self.task_repo.add(task)

        # 4. 启动后台 runner
        if self.event_service and self.tool_registry:
            asyncio_task = asyncio.create_task(
                self._run_agent_loop(
                    agent_id=agent_id,
                    session_id=session_id,
                    task=task,
                    content=content,
                    model=model,
                    max_turns=max_turns,
                    workspace=workspace,
                )
            )
            asyncio_task.add_done_callback(
                lambda t: logger.info("Agent loop task %s finished", task.id)
            )

        return {
            "user_message": user_msg,
            "task_id": task.id,
            "asyncio_task": asyncio_task if (self.event_service and self.tool_registry) else None,
        }

    async def _run_agent_loop(
        self,
        agent_id: str,
        session_id: str,
        task: Task,
        content: str,
        model: str,
        max_turns: int,
        workspace: str,
    ) -> None:
        """后台 Agent Loop Runner"""
        try:
            # 步骤 A: 构建 system_prompt
            agent = await self.agent_repo.get_by_id(agent_id)
            if not agent:
                raise ValueError(f"Agent {agent_id} not found")

            system_prompt = PromptBuilder.build_system_prompt(agent)

            # 步骤 B: 加载会话历史 → LangChain 消息格式
            # 注意：历史 AIMessage 不传 tool_calls，因为对应的 ToolMessage
            # 没有一并回放，传入会触发 LLM provider 报错（tool_call 无对应结果），
            # 同时也避免旧数据中 tool_calls 缺少 keyword-only 参数 `args` 时
            # AIMessage 构造抛出 `tool_call() missing 1 required keyword-only argument: 'args'`。
            history_messages = await self.message_repo.list_by_session(session_id, limit=20)
            messages = []
            for msg in history_messages:
                # 跳过当前这条用户消息（会在 initial_state 中作为 user_message 处理）
                if msg.role == SessionMessageRole.USER:
                    messages.append(HumanMessage(content=msg.content))
                elif msg.role == SessionMessageRole.ASSISTANT:
                    messages.append(AIMessage(content=msg.content or ""))
                elif msg.role == SessionMessageRole.TOOL_SUMMARY:
                    messages.append(HumanMessage(content=f"[Tool Results] {msg.content}"))

            # 步骤 C: 创建 LLM 实例 + 绑定工具
            llm = create_chat_model(model=model or None)
            if self.tool_registry and self.tool_registry.tool_count > 0:
                tool_schemas = _tool_defs_to_openai_functions(self.tool_registry)
                llm = llm.bind_tools(tool_schemas)

            # 步骤 D: 构建初始 AgentState
            initial_state = {
                "messages": messages,
                "task_id": task.id,
                "workspace": workspace,
                "user_message": content,
                "current_turn": 0,
                "max_turns": max_turns,
                "phase": "idle",
                "should_end": False,
                "pending_tool_calls": [],
                "tool_results": {},
                "loop_detection_count": 0,
                "loop_detected": False,
                "loop_type": None,
                "stuck_detection_count": 0,
                "stuck_detected": False,
                "stuck_type": None,
                "current_llm_text": "",
                "system_prompt": system_prompt,
                "final_result": None,
                "error": None,
            }

            # 步骤 E: 编译并执行 LangGraph
            graph = AgentWorkflowBuilder().build()
            graph_config = {
                "configurable": {
                    "llm": llm,
                    "event_service": self.event_service,
                    "tool_registry": self.tool_registry,
                }
            }

            await self.event_service.emit(task.id, "task-started", {"taskId": task.id})

            result = await graph.ainvoke(initial_state, graph_config)

            # 步骤 F: 执行完成后处理
            final_result = result.get("final_result")
            error = result.get("error")

            # 收集工具调用信息（带 args，保证历史完整性）
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
                            all_tool_calls.append({
                                "name": t.get("name", ""),
                                "args": t.get("args", {}),
                                "id": t.get("id", ""),
                            })
                        else:
                            all_tool_calls.append({
                                "name": getattr(t, "name", ""),
                                "args": getattr(t, "args", {}) or {},
                                "id": getattr(t, "id", ""),
                            })

            # 保存 assistant 消息
            assistant_content = final_result or error or ""
            if not assistant_content:
                # 从最后一条 AI 消息提取
                for msg in reversed(result.get("messages", [])):
                    msg_content = ""
                    if isinstance(msg, dict):
                        msg_content = msg.get("content", "")
                    elif hasattr(msg, "content"):
                        msg_content = msg.content or ""
                    if msg_content:
                        assistant_content = msg_content
                        break

            assistant_msg = SessionMessage(
                session_id=session_id,
                task_id=task.id,
                role=SessionMessageRole.ASSISTANT,
                content=assistant_content,
                tool_calls=all_tool_calls,
                tool_results=all_tool_results,
                status=MessageStatus.ERROR if error else MessageStatus.COMPLETED,
                error=error,
            )
            assistant_msg = await self.message_repo.add(assistant_msg)

            # 更新 Task 状态
            if self.task_repo:
                task.status = TaskStatus.FAILED if error else TaskStatus.COMPLETED
                task.completed_at = datetime.now()
                task.result = final_result
                task.error = error
                await self.task_repo.update(task)

            # 更新 Session 元数据
            session = await self.session_repo.get_by_id(session_id)
            if session:
                session.update_metadata(assistant_content)
                await self.session_repo.update(session)

            # 发射 session-message-saved 事件（必须在 task-completed 之前，
            # 因为前端收到 task-completed 后会断开 SSE 连接）
            await self.event_service.emit(
                task.id,
                "session-message-saved",
                {
                    "message": {
                        "id": assistant_msg.id,
                        "session_id": assistant_msg.session_id,
                        "task_id": assistant_msg.task_id,
                        "role": assistant_msg.role.value,
                        "content": assistant_msg.content,
                        "tool_calls": assistant_msg.tool_calls,
                        "tool_results": assistant_msg.tool_results,
                        "status": assistant_msg.status.value,
                        "error": assistant_msg.error,
                        "cost": assistant_msg.cost,
                        "created_at": assistant_msg.created_at.isoformat(),
                    }
                },
            )

            # 发射完成事件（最后发送，前端收到后断开连接）
            if error:
                await self.event_service.emit(
                    task.id, "task-failed", {"taskId": task.id, "error": error}
                )
            else:
                await self.event_service.emit(
                    task.id, "task-completed", {"taskId": task.id, "result": final_result}
                )

        except asyncio.CancelledError:
            logger.info("Agent loop cancelled for task %s", task.id)
            if self.task_repo:
                task.status = TaskStatus.CANCELLED
                task.completed_at = datetime.now()
                task.error = "cancelled"
                await self.task_repo.update(task)
            if self.event_service:
                await self.event_service.emit(
                    task.id, "task-failed", {"taskId": task.id, "error": "cancelled"}
                )
        except Exception as e:
            logger.exception("Agent loop failed for task %s: %s", task.id, e)
            if self.task_repo:
                task.status = TaskStatus.FAILED
                task.completed_at = datetime.now()
                task.error = str(e)
                await self.task_repo.update(task)
            if self.event_service:
                await self.event_service.emit(
                    task.id, "task-failed", {"taskId": task.id, "error": str(e)}
                )
