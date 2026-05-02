"""应用层 - SendMessage 用例

核心编排用例：用户发送消息 → 创建 Task → 异步启动 Agent Loop。
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from langchain_core.messages import AIMessage, HumanMessage

from src.application.use_cases.agent_workflow import (
    AgentWorkflowBuilder,
    route_after_tool_execute,
)
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
from src.domain.services import IEventEmitter
from src.domain.services.prompt_builder import PromptBuilder
from src.infrastructure.llm.model_factory import create_chat_model
from src.infrastructure.agent.nodes.tool_execute_node import tool_execute_node
from src.infrastructure.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


def _tool_defs_to_openai_functions(tool_registry: ToolRegistry) -> list:
    """将工具转换为 OpenAI function schema 格式（供 bind_tools 使用）"""
    schemas = []
    for tool in tool_registry.list_tools():
        td = tool.to_tool_def()
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


def _build_message_event_payload(message: SessionMessage) -> Dict[str, Any]:
    """构建 session:message:saved 事件载荷。"""
    return {
        "message": {
            "id": message.id,
            "session_id": message.session_id,
            "task_id": message.task_id,
            "role": message.role.value,
            "content": message.content,
            "tool_calls": message.tool_calls,
            "tool_results": message.tool_results,
            "status": message.status.value,
            "error": message.error,
            "cost": message.cost,
            "created_at": message.created_at.isoformat(),
        }
    }


@dataclass
class PendingApprovalContext:
    """单进程内存态审批上下文。"""

    use_case: "SendMessageUseCase"
    task: Task
    agent_id: str
    session_id: str
    model: Optional[str]
    max_turns: int
    workspace: str
    state: Dict[str, Any]
    approval_request: Dict[str, Any]
    resume_future: Optional[asyncio.Future] = None
    tool_registry: Optional[ToolRegistry] = None
    step_id: Optional[int] = None


class SendMessageUseCase:
    """发送消息用例 — 编排 Session 操作 + Agent Loop 启动"""

    def __init__(
        self,
        agent_repo: IAgentRepository,
        session_repo: ISessionRepository,
        message_repo: ISessionMessageRepository,
        task_repo: Optional[ITaskRepository] = None,
        event_emitter: Optional[IEventEmitter] = None,
        tool_registry: Optional[ToolRegistry] = None,
        approval_store: Optional[dict[str, PendingApprovalContext]] = None,
        running_tasks: Optional[dict[str, asyncio.Task]] = None,
    ):
        self.agent_repo = agent_repo
        self.session_repo = session_repo
        self.message_repo = message_repo
        self.task_repo = task_repo
        self.event_emitter = event_emitter
        self.tool_registry = tool_registry
        self.approval_store = approval_store if approval_store is not None else {}
        self.running_tasks = running_tasks if running_tasks is not None else {}

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
        asyncio_task: asyncio.Task | None = None
        if self.event_emitter and self.tool_registry:
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
            "asyncio_task": asyncio_task if (self.event_emitter and self.tool_registry) else None,
        }

    def _build_llm(self, model: Optional[str], tool_registry: Optional[ToolRegistry], agent_id: str):
        llm = create_chat_model(model=model or None)
        if tool_registry and tool_registry.tool_count > 0:
            tool_schemas = _tool_defs_to_openai_functions(tool_registry)
            llm = llm.bind_tools(tool_schemas)
            logger.info("binding-tools agent %s Tool schemas: %s", agent_id, tool_schemas)
        return llm

    def _build_graph_config(
        self,
        llm,
        tool_registry: Optional[ToolRegistry],
        agent_id: str,
        model: Optional[str],
    ) -> Dict[str, Any]:
        return {
            "configurable": {
                "llm": llm,
                "event_emitter": self.event_emitter,
                "event_service": self.event_emitter,
                "tool_registry": tool_registry,
                "agent_id": agent_id,
                "llm_model": model,
                "send_message_use_case": self,
            }
        }

    @staticmethod
    def _merge_state(base_state: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(base_state)
        if "messages" in update:
            merged["messages"] = list(base_state.get("messages", [])) + list(update["messages"])
        for key, value in update.items():
            if key == "messages":
                continue
            merged[key] = value
        return merged

    @staticmethod
    def _build_approval_message(approval_request: Dict[str, Any]) -> str:
        tool_name = approval_request.get("toolName", "tool")
        tool_input = approval_request.get("input", {})
        return (
            f"Approval required before running `{tool_name}`.\n\n"
            f"Input:\n{tool_input}"
        )

    async def _pause_for_approval(
        self,
        *,
        task: Task,
        session_id: str,
        agent_id: str,
        model: Optional[str],
        max_turns: int,
        workspace: str,
        result: Dict[str, Any],
    ) -> None:
        approval_request = result.get("approval_request") or {}
        final_turn = result.get("current_turn", task.current_turn)
        previous_phase = result.get("phase", "tool_executing")
        assistant_content = self._build_approval_message(approval_request)

        assistant_msg = SessionMessage(
            session_id=session_id,
            task_id=task.id,
            role=SessionMessageRole.ASSISTANT,
            content=assistant_content,
            tool_calls=[
                {
                    "name": approval_request.get("toolName", ""),
                    "id": approval_request.get("toolCallId", ""),
                }
            ],
            tool_results=[
                {
                    "tool_name": approval_request.get("toolName", ""),
                    "id": approval_request.get("toolCallId", ""),
                    "status": "approval_required",
                    "result": approval_request.get("message", ""),
                }
            ],
            status=MessageStatus.COMPLETED,
        )
        assistant_msg = await self.message_repo.add(assistant_msg)

        if self.task_repo:
            task.status = TaskStatus.PAUSED
            task.current_turn = final_turn
            task.error = None
            task.completed_at = None
            await self.task_repo.update(task)

        result["phase"] = "paused"
        self.approval_store[task.id] = PendingApprovalContext(
            use_case=self,
            task=task,
            agent_id=agent_id,
            session_id=session_id,
            model=model,
            max_turns=max_turns,
            workspace=workspace,
            state=result,
            approval_request=approval_request,
        )

        await self.event_emitter.emit_phase_changed(
            task.id,
            "paused",
            previous_phase,
            final_turn,
        )
        await self.event_emitter.emit(
            task.id,
            "session:message:saved",
            _build_message_event_payload(assistant_msg),
        )
        await self.event_emitter.emit(
            task.id,
            "approval:requested",
            approval_request,
        )
        await self.event_emitter.emit(
            task.id,
            "task:paused",
            {"reason": "approval_required"},
        )

    async def _finalize_terminal_result(
        self,
        *,
        task: Task,
        session_id: str,
        result: Dict[str, Any],
    ) -> None:
        self.approval_store.pop(task.id, None)
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
                            {"name": t.get("name", ""), "args": t.get("args", {}), "id": t.get("id", "")}
                        )
                    else:
                        all_tool_calls.append(
                            {
                                "name": getattr(t, "name", ""),
                                "args": getattr(t, "args", {}) or {},
                                "id": getattr(t, "id", ""),
                            }
                        )

        for tool_call_id, tool_result in (result.get("tool_results") or {}).items():
            all_tool_results.append(
                {
                    "tool_name": tool_result.get("tool_name", ""),
                    "id": tool_call_id,
                    "status": tool_result.get("status", "success"),
                    "result": tool_result.get("output") or tool_result.get("error") or "",
                }
            )

        assistant_content = final_result or error or ""
        if not assistant_content:
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

        if self.task_repo:
            task.status = TaskStatus.FAILED if error else TaskStatus.COMPLETED
            task.current_turn = final_turn
            task.completed_at = datetime.now()
            task.result = final_result
            task.error = error
            await self.task_repo.update(task)

        session = await self.session_repo.get_by_id(session_id)
        if session:
            session.update_metadata(assistant_content)
            await self.session_repo.update(session)

        await self.event_emitter.emit_phase_changed(
            task.id,
            "failed" if error else "complete",
            previous_phase,
            final_turn,
        )
        await self.event_emitter.emit(
            task.id,
            "session:message:saved",
            _build_message_event_payload(assistant_msg),
        )
        if error:
            await self.event_emitter.emit(task.id, "task:failed", {"error": error})
        else:
            await self.event_emitter.emit(task.id, "task:completed", {"result": final_result})

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
            logger.info("building-system_prompt agent %s System prompt: %s", agent_id, system_prompt)

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
            llm = self._build_llm(model, self.tool_registry, agent_id)

            # 步骤 D: 构建初始 AgentState
            initial_state = {
                "messages": messages,
                "task_id": task.id,
                "workspace": workspace,
                "user_message": content,
                "task_start_message_count": len(messages),
                "current_turn": 0,
                "max_turns": max_turns,
                "phase": "idle",
                "should_end": False,
                "is_complete": False,
                "pending_tool_calls": [],
                "tool_results": {},
                "awaiting_user_input": False,
                "awaiting_approval": False,
                "approval_request": None,
                "approved_tool_call_ids": [],
                "last_executed_tool_call_ids": [],
                "loop_detection_count": 0,
                "loop_detected": False,
                "loop_type": None,
                "stuck_detection_count": 0,
                "stuck_detected": False,
                "stuck_type": None,
                "current_llm_text": "",
                "empty_retry_count": 0,
                "planning_retry_count": 0,
                "system_prompt": system_prompt,
                "final_result": None,
                "error": None,
            }

            # 步骤 E: 编译并执行 LangGraph
            graph = AgentWorkflowBuilder().build()
            graph_config = self._build_graph_config(llm, self.tool_registry, agent_id, model)

            await self.event_emitter.emit(task.id, "task:started", {})

            result = await graph.ainvoke(initial_state, graph_config)
            if result.get("awaiting_approval"):
                await self._pause_for_approval(
                    task=task,
                    session_id=session_id,
                    agent_id=agent_id,
                    model=model,
                    max_turns=max_turns,
                    workspace=workspace,
                    result=result,
                )
                return

            await self._finalize_terminal_result(
                task=task,
                session_id=session_id,
                result=result,
            )

        except asyncio.CancelledError:
            logger.info("Agent loop cancelled for task %s", task.id)
            self.approval_store.pop(task.id, None)
            if self.task_repo:
                task.status = TaskStatus.CANCELLED
                task.completed_at = datetime.now()
                task.error = "cancelled"
                await self.task_repo.update(task)
            if self.event_emitter:
                await self.event_emitter.emit_phase_changed(
                    task.id,
                    "cancelled",
                    "thinking",
                    task.current_turn,
                )
                await self.event_emitter.emit(
                    task.id, "task:cancelled", {}
                )
        except Exception as e:
            logger.exception("Agent loop failed for task %s: %s", task.id, e)
            self.approval_store.pop(task.id, None)
            if self.task_repo:
                task.status = TaskStatus.FAILED
                task.completed_at = datetime.now()
                task.error = str(e)
                await self.task_repo.update(task)
            if self.event_emitter:
                await self.event_emitter.emit_phase_changed(
                    task.id,
                    "failed",
                    "thinking",
                    task.current_turn,
                )
                await self.event_emitter.emit(
                    task.id, "task:failed", {"error": str(e)}
                )

    async def resolve_pending_approval(self, task_id: str, approved: bool) -> asyncio.Task | None:
        context = self.approval_store.get(task_id)
        if context is None:
            raise ValueError(f"No pending approval for task {task_id}")

        if approved:
            return await self._resume_after_approval(context)

        await self._reject_approval(context)
        return None

    async def _resume_after_approval(
        self,
        context: PendingApprovalContext,
    ) -> asyncio.Task:
        if getattr(context, "resume_future", None) is not None:
            return await self._resume_sub_agent_after_approval(context)

        self.approval_store.pop(context.task.id, None)

        task = context.task
        paused_state = dict(context.state)
        approved_tool_call_ids = list(paused_state.get("approved_tool_call_ids", []))
        tool_call_id = context.approval_request.get("toolCallId", "")
        if tool_call_id and tool_call_id not in approved_tool_call_ids:
            approved_tool_call_ids.append(tool_call_id)

        paused_state["approved_tool_call_ids"] = approved_tool_call_ids
        paused_state["awaiting_approval"] = False
        paused_state["approval_request"] = None
        paused_state["final_result"] = None
        paused_state["phase"] = "paused"

        if self.task_repo:
            task.status = TaskStatus.RUNNING
            task.error = None
            task.completed_at = None
            await self.task_repo.update(task)

        await self.event_emitter.emit(
            task.id,
            "approval:resolved",
            {
                **context.approval_request,
                "approved": True,
            },
        )
        await self.event_emitter.emit(task.id, "task:resumed", {})

        resume_task = asyncio.create_task(
            self._continue_after_approval(
                task=task,
                session_id=context.session_id,
                agent_id=context.agent_id,
                model=context.model,
                workspace=context.workspace,
                resumed_state=paused_state,
            )
        )
        self.running_tasks[task.id] = resume_task
        resume_task.add_done_callback(lambda _: self.running_tasks.pop(task.id, None))
        return resume_task

    async def _continue_after_approval(
        self,
        *,
        task: Task,
        session_id: str,
        agent_id: str,
        model: Optional[str],
        workspace: str,
        resumed_state: Dict[str, Any],
    ) -> None:
        try:
            llm = self._build_llm(model, self.tool_registry, agent_id)
            graph_config = self._build_graph_config(llm, self.tool_registry, agent_id, model)

            tool_update = await tool_execute_node(resumed_state, graph_config)
            state_after_tools = self._merge_state(resumed_state, tool_update)
            next_step = route_after_tool_execute(state_after_tools)

            if next_step == "__end__":
                result = state_after_tools
            else:
                graph = AgentWorkflowBuilder().build()
                result = await graph.ainvoke(state_after_tools, graph_config)

            if result.get("awaiting_approval"):
                await self._pause_for_approval(
                    task=task,
                    session_id=session_id,
                    agent_id=agent_id,
                    model=model,
                    max_turns=task.max_turns,
                    workspace=workspace,
                    result=result,
                )
                return

            await self._finalize_terminal_result(
                task=task,
                session_id=session_id,
                result=result,
            )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("Resumed agent loop failed for task %s: %s", task.id, e)
            if self.task_repo:
                task.status = TaskStatus.FAILED
                task.completed_at = datetime.now()
                task.error = str(e)
                await self.task_repo.update(task)
            await self.event_emitter.emit_phase_changed(
                task.id,
                "failed",
                "paused",
                task.current_turn,
            )
            await self.event_emitter.emit(task.id, "task:failed", {"error": str(e)})

    async def _resume_sub_agent_after_approval(
        self,
        context: PendingApprovalContext,
    ) -> asyncio.Task:
        self.approval_store.pop(context.task.id, None)

        task = context.task
        paused_state = dict(context.state)
        approved_tool_call_ids = list(paused_state.get("approved_tool_call_ids", []))
        tool_call_id = context.approval_request.get("toolCallId", "")
        if tool_call_id and tool_call_id not in approved_tool_call_ids:
            approved_tool_call_ids.append(tool_call_id)

        paused_state["approved_tool_call_ids"] = approved_tool_call_ids
        paused_state["awaiting_approval"] = False
        paused_state["approval_request"] = None
        paused_state["final_result"] = None
        paused_state["phase"] = "paused"

        if self.task_repo:
            task.status = TaskStatus.RUNNING
            task.error = None
            task.completed_at = None
            await self.task_repo.update(task)

        await self.event_emitter.emit(
            task.id,
            "approval:resolved",
            {
                **context.approval_request,
                "approved": True,
            },
        )
        await self.event_emitter.emit(task.id, "task:resumed", {})

        resume_task = asyncio.create_task(
            self._continue_sub_agent_after_approval(
                context=context,
                resumed_state=paused_state,
            )
        )
        return resume_task

    async def _continue_sub_agent_after_approval(
        self,
        *,
        context: PendingApprovalContext,
        resumed_state: Dict[str, Any],
    ) -> None:
        try:
            tool_registry = context.tool_registry or self.tool_registry
            llm = self._build_llm(context.model, tool_registry, context.agent_id)
            graph_config = self._build_graph_config(
                llm,
                tool_registry,
                context.agent_id,
                context.model,
            )

            tool_update = await tool_execute_node(resumed_state, graph_config)
            state_after_tools = self._merge_state(resumed_state, tool_update)
            next_step = route_after_tool_execute(state_after_tools)

            if next_step == "__end__":
                result = state_after_tools
            else:
                graph = AgentWorkflowBuilder().build()
                result = await graph.ainvoke(state_after_tools, graph_config)

            if result.get("awaiting_approval"):
                await self._pause_sub_agent_for_approval(
                    parent_task=context.task,
                    agent_id=context.agent_id,
                    model=context.model,
                    workspace=context.workspace,
                    result=result,
                    sub_tool_registry=tool_registry,
                    step_id=context.step_id or 0,
                    resume_future=context.resume_future,
                )
                return

            if context.resume_future and not context.resume_future.done():
                context.resume_future.set_result(
                    {
                        "task_id": resumed_state.get("task_id"),
                        "final_result": result.get("final_result"),
                        "error": result.get("error"),
                    }
                )
        except Exception as e:
            logger.exception(
                "Resumed sub-agent loop failed for parent task %s: %s",
                context.task.id,
                e,
            )
            if context.resume_future and not context.resume_future.done():
                context.resume_future.set_result(
                    {
                        "task_id": resumed_state.get("task_id"),
                        "final_result": None,
                        "error": str(e),
                    }
                )

    async def _reject_sub_agent_approval(self, context: PendingApprovalContext) -> None:
        self.approval_store.pop(context.task.id, None)
        approval_request = context.approval_request

        await self.event_emitter.emit(
            context.task.id,
            "approval:resolved",
            {
                **approval_request,
                "approved": False,
            },
        )

        if self.task_repo:
            context.task.status = TaskStatus.RUNNING
            context.task.error = None
            await self.task_repo.update(context.task)

        await self.event_emitter.emit(context.task.id, "task:resumed", {})

        if context.resume_future and not context.resume_future.done():
            context.resume_future.set_result(
                {
                    "task_id": context.state.get("task_id"),
                    "final_result": None,
                    "error": (
                        f"Approval denied for tool "
                        f"'{approval_request.get('toolName', 'tool')}'"
                    ),
                }
            )

    async def _reject_approval(self, context: PendingApprovalContext) -> None:
        if getattr(context, "resume_future", None) is not None:
            await self._reject_sub_agent_approval(context)
            return

        self.approval_store.pop(context.task.id, None)
        task = context.task
        approval_request = context.approval_request

        await self.event_emitter.emit(
            task.id,
            "approval:resolved",
            {
                **approval_request,
                "approved": False,
            },
        )
        await self._finalize_terminal_result(
            task=task,
            session_id=context.session_id,
            result={
                **context.state,
                "phase": "paused",
                "error": f"Approval denied for tool '{approval_request.get('toolName', 'tool')}'",
                "final_result": None,
            },
        )

    @staticmethod
    def _build_sub_agent_prompt(
        *,
        step: Dict[str, Any],
        plan_goal: Optional[str],
        previous_step_results: Optional[Dict[int, Dict[str, Any]]],
    ) -> str:
        lines = [
            "你是主 Agent 创建的子 Agent，只负责执行当前 plan 步骤。",
            f"主计划目标：{plan_goal or '未提供'}",
            f"当前步骤 {step.get('id')}: {step.get('description', '')}",
        ]

        if previous_step_results:
            lines.append("")
            lines.append("前序步骤结果：")
            for step_id, result in sorted(previous_step_results.items()):
                lines.append(
                    f"- Step {step_id}: status={result.get('status')}, "
                    f"result={result.get('result') or result.get('error') or ''}"
                )

        lines.extend(
            [
                "",
                "执行要求：",
                "- 只完成当前步骤，不要重新规划整个任务。",
                "- 需要外部信息时使用可用工具。",
                "- 如果当前步骤需要写文件，调用 file_write；该工具可能触发用户审批。",
                "- 完成后直接返回本步骤的关键结果，供主 Agent 更新 plan。",
            ]
        )
        return "\n".join(lines)

    async def _get_task_for_approval(self, task_id: str) -> Task:
        if self.task_repo:
            task = await self.task_repo.get_by_id(task_id)
            if task:
                return task
        return Task(id=task_id, status=TaskStatus.PAUSED)

    async def _pause_sub_agent_for_approval(
        self,
        *,
        parent_task: Task,
        agent_id: str,
        model: Optional[str],
        workspace: str,
        result: Dict[str, Any],
        sub_tool_registry: Optional[ToolRegistry],
        step_id: int,
        resume_future: asyncio.Future,
    ) -> None:
        approval_request = {
            **(result.get("approval_request") or {}),
            "subTaskId": result.get("task_id"),
            "stepId": step_id,
        }
        final_turn = result.get("current_turn", parent_task.current_turn)
        previous_phase = result.get("phase", "tool_executing")
        assistant_content = self._build_approval_message(approval_request)
        session_id = parent_task.session_id or ""

        if session_id:
            assistant_msg = SessionMessage(
                session_id=session_id,
                task_id=parent_task.id,
                role=SessionMessageRole.ASSISTANT,
                content=assistant_content,
                tool_calls=[
                    {
                        "name": approval_request.get("toolName", ""),
                        "id": approval_request.get("toolCallId", ""),
                    }
                ],
                tool_results=[
                    {
                        "tool_name": approval_request.get("toolName", ""),
                        "id": approval_request.get("toolCallId", ""),
                        "status": "approval_required",
                        "result": approval_request.get("message", ""),
                    }
                ],
                status=MessageStatus.COMPLETED,
            )
            assistant_msg = await self.message_repo.add(assistant_msg)
        else:
            assistant_msg = None

        if self.task_repo:
            parent_task.status = TaskStatus.PAUSED
            parent_task.current_turn = final_turn
            parent_task.error = None
            parent_task.completed_at = None
            await self.task_repo.update(parent_task)

        result["phase"] = "paused"
        self.approval_store[parent_task.id] = PendingApprovalContext(
            use_case=self,
            task=parent_task,
            agent_id=agent_id,
            session_id=session_id,
            model=model,
            max_turns=parent_task.max_turns,
            workspace=workspace,
            state=result,
            approval_request=approval_request,
            resume_future=resume_future,
            tool_registry=sub_tool_registry,
            step_id=step_id,
        )

        await self.event_emitter.emit_phase_changed(
            parent_task.id,
            "paused",
            previous_phase,
            final_turn,
        )
        if assistant_msg:
            await self.event_emitter.emit(
                parent_task.id,
                "session:message:saved",
                _build_message_event_payload(assistant_msg),
            )
        await self.event_emitter.emit(
            parent_task.id,
            "approval:requested",
            approval_request,
        )
        await self.event_emitter.emit(
            parent_task.id,
            "task:paused",
            {"reason": "approval_required"},
        )

    async def _run_sub_agent(
        self,
        step: Dict[str, Any],
        parent_task_id: str,
        workspace: str,
        agent_id: str,
        model: str,
        plan_goal: Optional[str] = None,
        previous_step_results: Optional[Dict[int, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """创建并运行子Agent
        
        与主Agent的区别:
        1. tool_registry 去掉 plan 和 clarify
        2. tool_registry 添加 plan_update
        3. state.is_sub_agent = True
        4. state.parent_task_id = parent_task_id
        5. 复用同一个 StateGraph (AgentWorkflowBuilder().build())
        
        Args:
            step: PlanStep字典,包含id和description
            parent_task_id: 父Agent的task_id
            workspace: 工作目录
            agent_id: Agent ID
            model: LLM模型
            
        Returns:
            子Agent执行结果
        """
        from src.domain.entities.agent_state import AgentState
        from src.application.use_cases.agent_workflow import AgentWorkflowBuilder
        from langchain_core.messages import HumanMessage
        
        logger.info(
            "Creating sub-agent for step %d: %s",
            step.get("id"),
            step.get("description"),
        )
        step_prompt = self._build_sub_agent_prompt(
            step=step,
            plan_goal=plan_goal,
            previous_step_results=previous_step_results,
        )
        
        # 1. 创建子Agent的tool_registry
        sub_tool_registry = self._create_sub_agent_tool_registry(
            parent_tool_registry=self.tool_registry,
            parent_task_id=parent_task_id,
            step_id=step.get("id", 0),
        )
        
        # 2. 构建子Agent的initial_state
        initial_state: AgentState = {
            "messages": [
                HumanMessage(content=step_prompt)
            ],
            "task_id": f"sub-{parent_task_id}-{step.get('id', 0)}",
            "workspace": workspace,
            "user_message": step_prompt,
            "task_start_message_count": 1,
            "current_turn": 0,
            "max_turns": 50,  # 子Agent最大轮次限制
            "phase": "idle",
            "should_end": False,
            "is_complete": False,
            "pending_tool_calls": [],
            "tool_results": {},
            "awaiting_user_input": False,
            "awaiting_approval": False,
            "approval_request": None,
            "approved_tool_call_ids": [],
            "last_executed_tool_call_ids": [],
            "loop_detection_count": 0,
            "loop_detected": False,
            "loop_type": None,
            "stuck_detection_count": 0,
            "stuck_detected": False,
            "stuck_type": None,
            "current_llm_text": "",
            "empty_retry_count": 0,
            "planning_retry_count": 0,
            "system_prompt": "",  # 子Agent使用默认system_prompt
            "final_result": None,
            "error": None,
            # Plan相关字段
            "plan": None,
            "plan_results": {},
            "is_sub_agent": True,
            "parent_task_id": parent_task_id,
        }
        
        # 3. 创建LLM实例
        llm = create_chat_model(model=model or None)
        if sub_tool_registry and sub_tool_registry.tool_count > 0:
            tool_schemas = _tool_defs_to_openai_functions(sub_tool_registry)
            llm = llm.bind_tools(tool_schemas)
        
        # 4. 编译并执行LangGraph
        graph = AgentWorkflowBuilder().build()
        graph_config = {
            "configurable": {
                "llm": llm,
                "event_emitter": self.event_emitter,
                "event_service": self.event_emitter,
                "tool_registry": sub_tool_registry,
                "agent_id": agent_id,
                "llm_model": model,
                "send_message_use_case": self,  # 传入self以便子Agent回调
            }
        }
        
        # 发射子Agent开始事件
        await self.event_emitter.emit(
            parent_task_id,
            "sub_agent:started",
            {
                "sub_task_id": initial_state["task_id"],
                "step_id": step.get("id"),
                "description": step.get("description"),
            },
        )
        
        try:
            result = await graph.ainvoke(initial_state, graph_config)

            if result.get("awaiting_approval"):
                parent_task = await self._get_task_for_approval(parent_task_id)
                resume_future: asyncio.Future = asyncio.get_running_loop().create_future()
                await self._pause_sub_agent_for_approval(
                    parent_task=parent_task,
                    agent_id=agent_id,
                    model=model,
                    workspace=workspace,
                    result=result,
                    sub_tool_registry=sub_tool_registry,
                    step_id=step.get("id", 0),
                    resume_future=resume_future,
                )
                result = await resume_future
            
            sub_agent_failed = bool(result.get("error"))
            await self.event_emitter.emit(
                parent_task_id,
                "sub_agent:failed" if sub_agent_failed else "sub_agent:completed",
                {
                    "sub_task_id": initial_state["task_id"],
                    "step_id": step.get("id"),
                    "status": "failed" if sub_agent_failed else "completed",
                    "error": result.get("error"),
                },
            )
            
            return {
                "task_id": initial_state["task_id"],
                "final_result": result.get("final_result"),
                "error": result.get("error"),
            }
            
        except Exception as e:
            logger.exception("Sub-agent failed for step %d", step.get("id"))
            
            # 发射子Agent失败事件
            await self.event_emitter.emit(
                parent_task_id,
                "sub_agent:failed",
                {
                    "sub_task_id": initial_state["task_id"],
                    "step_id": step.get("id"),
                    "error": str(e),
                },
            )
            
            return {
                "task_id": initial_state["task_id"],
                "final_result": None,
                "error": str(e),
            }
    
    def _create_sub_agent_tool_registry(
        self,
        parent_tool_registry: ToolRegistry,
        parent_task_id: str,
        step_id: int,
    ) -> ToolRegistry:
        """创建子Agent的工具注册表
        
        1. 复制父Agent的工具
        2. 排除 plan, plan_execute 和 clarify
        3. 添加 plan_update 工具(绑定parent_task_id和step_id)
        """
        from src.infrastructure.tools.pipeline import ExecutionPipeline
        from src.infrastructure.tools.middleware.security import SecurityMiddleware
        from src.infrastructure.tools.middleware.rate_limit import RateLimitMiddleware
        from src.infrastructure.tools.middleware.timeout import TimeoutMiddleware
        from src.infrastructure.tools.middleware.sandbox import SandboxMiddleware
        from src.domain.entities.tool import RegisteredTool, ToolContext, ToolResult
        
        # 构建中间件管道
        pipeline = ExecutionPipeline()
        pipeline.add_middleware(SecurityMiddleware(allowed_tools=None))
        pipeline.add_middleware(RateLimitMiddleware(global_max_per_minute=300))
        pipeline.add_middleware(TimeoutMiddleware())
        pipeline.add_middleware(SandboxMiddleware())
        
        # 创建新的Registry
        sub_registry = ToolRegistry(pipeline=pipeline)
        
        # 复制父Agent的工具(排除plan和clarify)
        for tool in parent_tool_registry.list_tools():
            if tool.name in ("plan", "plan_execute", "clarify"):
                continue
            sub_registry.register(tool)
        
        # 添加plan_update工具(需要绑定parent_task_id和step_id)
        plan_update_tool = self._create_plan_update_tool(parent_task_id, step_id)
        sub_registry.register(plan_update_tool)
        
        logger.info(
            "Sub-agent tool registry created: %d tools (step %d)",
            sub_registry.tool_count,
            step_id,
        )
        
        return sub_registry
    
    def _create_plan_update_tool(
        self,
        parent_task_id: str,
        step_id: int,
    ) -> RegisteredTool:
        """创建plan_update工具(绑定父任务信息)"""
        from src.domain.entities.tool import RegisteredTool, ToolContext, ToolResult
        
        async def plan_update_func(
            input: dict,
            context: Optional[ToolContext] = None,
        ) -> ToolResult:
            """plan_update工具函数"""
            step_id_input = input.get("step_id")
            status = input.get("status")
            result = input.get("result")
            
            if status not in ("completed", "failed"):
                return ToolResult(
                    output="Error: status must be 'completed' or 'failed'",
                    success=False,
                    error="invalid_input",
                )
            
            # 发射plan更新事件到父Agent
            if self.event_emitter:
                await self.event_emitter.emit(
                    parent_task_id,
                    "plan:step_completed",
                    {
                        "step_id": step_id,
                        "status": status,
                        "result": result,
                        "sub_task_id": context.task_id if context else None,
                    },
                )
            
            return ToolResult(
                output=f"Step {step_id} marked as {status}. Result recorded.",
                metadata={
                    "type": "plan_update",
                    "step_id": step_id,
                    "status": status,
                    "result": result,
                },
            )
        
        return RegisteredTool(
            name="plan_update",
            description="向主Agent报告当前plan步骤的完成状态。",
            func=plan_update_func,
            category="plan",
        )
