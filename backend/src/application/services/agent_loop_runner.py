"""应用层 - Agent Loop 运行器

编排 Agent Loop 的完整执行流程：
Prompt 组装 → 历史加载 → LLM 创建 → LangGraph 执行 → 终态处理。
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Optional

from langchain_core.messages import AIMessage, HumanMessage

from src.application.services.task_completion_service import TaskCompletionService
from src.domain.aggregates.session.session_message import SessionMessageRole
from src.domain.aggregates.task.task import Task, TaskStatus
from src.domain.entities.event_types import AgentEventType
from src.domain.interfaces.agent_workflow import IAgentWorkflowBuilder
from src.domain.interfaces.llm_provider import ILLMProvider
from src.domain.interfaces.prompt_context_interface import PromptContextInterface
from src.domain.repositories.agent_repository import IAgentRepository
from src.domain.repositories.session_message_repository import (
    ISessionMessageRepository,
)
from src.domain.repositories.session_repository import ISessionRepository
from src.domain.repositories.task_repository import ITaskRepository
from src.domain.repositories.tool_registry import IToolRegistry
from src.domain.services import IEventEmitter, ProxyEventEmitter
from src.domain.services.conversation_assembly import ConversationAssemblyService
from src.domain.services.prompt_assemble_service import PromptAssembleService
from src.domain.value_objects.prompt_template import PromptTemplate
from src.infrastructure.adapters.langchain_adapter import LangChainAdapter
from src.skills.skill_repository import ISkillRepository

logger = logging.getLogger(__name__)


class AgentLoopRunner:
    """后台 Agent Loop 运行器。

    编排 Agent Loop 的完整执行流程，包括：
    - Prompt 组装（11 层架构）
    - 会话历史加载与 Token 预算管理
    - LLM 实例创建与工具绑定
    - LangGraph 编译与执行
    - 异常处理（取消、出错）

    支持主 agent 模式和 sub-agent 模式。
    """

    def __init__(
        self,
        agent_repo: IAgentRepository,
        llm_provider: Optional[ILLMProvider],
        prompt_context: Optional[PromptContextInterface],
        message_repo: ISessionMessageRepository,
        skill_repo: Optional[ISkillRepository],
        task_repo: Optional[ITaskRepository],
        session_repo: Optional[ISessionRepository],
        event_emitter: Optional[IEventEmitter],
        tool_registry: Optional[IToolRegistry],
        workflow_builder: Optional[IAgentWorkflowBuilder],
        task_completion_service: TaskCompletionService,
        default_model: str = "gpt-4",
    ):
        self.agent_repo = agent_repo
        self.llm_provider = llm_provider
        self.prompt_context = prompt_context
        self.message_repo = message_repo
        self.skill_repo = skill_repo
        self.task_repo = task_repo
        self.session_repo = session_repo
        self.event_emitter = event_emitter
        self.tool_registry = tool_registry
        self.workflow_builder = workflow_builder
        self.task_completion_service = task_completion_service
        self.default_model = default_model

    async def run(
        self,
        *,
        agent_id: str,
        session_id: str,
        task: Task,
        content: str,
        model: Optional[str],
        max_turns: int,
        workspace: str,
        skill_ids: Optional[list[str]] = None,
        # Sub-agent 模式参数
        is_sub_agent: bool = False,
        parent_task_id: Optional[str] = None,
        sub_agent_description: Optional[str] = None,
        parent_system_prompt: Optional[str] = None,
        allowed_tools: Optional[list[str]] = None,
        persist_session_messages: bool = True,
        # 通过 graph config 注入供工具使用的 send_message_use_case 引用
        send_message_use_case: Any = None,
    ) -> None:
        """执行 Agent Loop。

        Args:
            agent_id: Agent ID
            session_id: Session ID
            task: Task 实体
            content: 用户消息内容
            model: LLM 模型名称
            max_turns: 最大轮次
            workspace: 工作目录
            skill_ids: 选中的 Skill ID 列表
            is_sub_agent: 是否为 sub-agent 模式
            parent_task_id: 父 task ID（sub-agent 模式）
            sub_agent_description: sub-agent 任务描述（sub-agent 模式）
            parent_system_prompt: 父 agent 的 system prompt（sub-agent 模式）
            allowed_tools: 允许的工具列表（sub-agent 模式）
            persist_session_messages: 是否持久化会话消息
            send_message_use_case: SendMessageUseCase 引用，通过 graph config 注入给工具
        """
        effective_event_emitter = self._build_event_emitter(
            is_sub_agent=is_sub_agent,
            parent_task_id=parent_task_id,
            sub_task_id=task.id,
        )
        if model is None:
            model = self.default_model

        try:
            # 步骤 A: 构建 system_prompt（使用 11 层 Prompt 架构）
            agent = await self.agent_repo.get_by_id(agent_id)
            if not agent:
                raise ValueError(f"Agent {agent_id} not found")

            # 使用新的 PromptAssembleService 组装 11 层 system_message
            template = PromptTemplate.from_agent(agent)
            assemble_service = PromptAssembleService()

            # 从 ToolRegistry 获取 ToolDef 列表（用于 Layer 5 工具描述）
            tool_defs = []
            if self.tool_registry:
                tool_defs = self.tool_registry.get_tool_defs()

            # 从 SkillRepository 获取选中的 SkillDef 列表（用于 Layer 8 注入）
            skill_defs = []
            if self.skill_repo and skill_ids:
                skill_defs = await self.skill_repo.get_by_ids(skill_ids)

            assembly_result = assemble_service.assemble(
                template=template,
                tools=tool_defs,
                skills=skill_defs,
                workspace=workspace,
                environment={
                    "platform": "darwin",
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "timezone": "Asia/Shanghai",
                },
                memory_enabled=bool(template.memory_md),
            )
            agent_system_prompt = assembly_result.system_message

            # 根据模式构建 system prompt
            system_prompt = self._build_system_prompt(
                is_sub_agent=is_sub_agent,
                parent_system_prompt=parent_system_prompt,
                sub_agent_description=sub_agent_description,
                agent_system_prompt=agent_system_prompt,
            )

            logger.info(
                "[Prompt Assembly] agent=%s | layers=%s | total_tokens=%d | static_prefix_tokens=%d",
                agent_id,
                assembly_result.layers,
                assembly_result.total_token_estimate,
                assembly_result.static_prefix_tokens,
            )

            # 步骤 B: 加载会话历史 → 通过 PromptContextInterface 构建 messages
            if is_sub_agent:
                # Sub-agent 是主 agent 的工具调用执行单元，只接收本次原子任务，
                # 不继承父 session 的 user/assistant/tool 历史。
                messages = [HumanMessage(content=content)]
            elif self.prompt_context:
                # 使用 PromptContextInterface 进行 Token 预算管理 + 裁剪
                history_messages = await self.message_repo.list_by_session(
                    session_id, limit=100
                )
                conversation_history = ConversationAssemblyService.assemble(
                    history_messages
                )
                max_tokens = 8000  # TODO: 从配置读取
                api_messages = await self.prompt_context.build_messages(
                    system_message=system_prompt,
                    history=conversation_history,
                    max_tokens=max_tokens,
                )
                messages = LangChainAdapter.dict_messages_to_langchain(api_messages)
            else:
                # 降级：无 PromptContextInterface 时的简单历史加载
                messages = await self._load_history_fallback(session_id)

            # 步骤 C: 创建 LLM 实例 + 绑定工具
            effective_tool_registry = self._build_tool_registry(
                is_sub_agent=is_sub_agent,
                allowed_tools=allowed_tools,
            )
            llm = self._build_llm(model, effective_tool_registry, agent_id)

            # 步骤 D: 构建初始 AgentState
            initial_state = self._build_initial_state(
                task=task,
                messages=messages,
                content=content,
                model=model,
                max_turns=max_turns,
                workspace=workspace,
                system_prompt=system_prompt,
                is_sub_agent=is_sub_agent,
                parent_task_id=parent_task_id,
            )

            # 步骤 E: 编译并执行 LangGraph
            if self.workflow_builder:
                graph = self.workflow_builder.build()
            else:
                from src.infrastructure.agent.workflow_builder import AgentWorkflowBuilder
                graph = AgentWorkflowBuilder.build()

            graph_config = {
                "configurable": {
                    "llm": llm,
                    "event_emitter": effective_event_emitter,
                    "event_service": effective_event_emitter,
                    "tool_registry": effective_tool_registry,
                    "agent_id": agent_id,
                    "llm_model": model,
                    "session_id": session_id,
                    # 注入 context 依赖，供工具使用
                    "send_message_use_case": send_message_use_case or self,
                    "task_repo": self.task_repo,
                    "parent_state": initial_state,
                    "parent_agent_id": agent_id,
                    "parent_session_id": session_id,
                    "parent_task_id": parent_task_id or task.id,
                }
            }

            await effective_event_emitter.emit(task.id, AgentEventType.TASK_STARTED, {})

            result = await graph.ainvoke(initial_state, graph_config)

            await self.task_completion_service.finalize(
                task=task,
                session_id=session_id,
                result=result,
                event_emitter=effective_event_emitter,
                persist_session_messages=persist_session_messages,
            )

        except asyncio.CancelledError:
            logger.info("Agent loop cancelled for task %s", task.id)
            if self.task_repo:
                task.status = TaskStatus.CANCELLED
                task.completed_at = datetime.now()
                task.error = "cancelled"
                await self.task_repo.update(task)
            if effective_event_emitter:
                await effective_event_emitter.emit_phase_changed(
                    task.id,
                    "cancelled",
                    "thinking",
                    task.current_turn,
                )
                await effective_event_emitter.emit(
                    task.id, AgentEventType.TASK_CANCELLED, {}
                )
        except Exception as e:
            logger.exception("Agent loop failed for task %s: %s", task.id, e)
            if self.task_repo:
                task.status = TaskStatus.FAILED
                task.completed_at = datetime.now()
                task.error = str(e)
                await self.task_repo.update(task)
            if effective_event_emitter:
                await effective_event_emitter.emit_phase_changed(
                    task.id,
                    "failed",
                    "thinking",
                    task.current_turn,
                )
                await effective_event_emitter.emit(
                    task.id, AgentEventType.TASK_FAILED, {"error": str(e)}
                )

    # ── 工厂方法 ──────────────────────────────────────────────

    def _build_llm(
        self,
        model: Optional[str],
        tool_registry: Optional[IToolRegistry],
        agent_id: str,
    ):
        """创建 LLM 实例并绑定工具。"""
        llm = self.llm_provider.create_chat_model(
            model=model or None) if self.llm_provider else None
        if llm is None:
            raise RuntimeError("LLM Provider is not configured")

        if tool_registry and tool_registry.tool_count > 0:
            tool_schemas = LangChainAdapter.tool_defs_to_openai_functions(tool_registry)
            llm = llm.bind_tools(tool_schemas)
            logger.info("binding-tools agent %s Tool schemas: %s",
                        agent_id, tool_schemas)
        return llm

    def _build_system_prompt(
        self,
        is_sub_agent: bool,
        parent_system_prompt: Optional[str],
        sub_agent_description: Optional[str],
        agent_system_prompt: str,
    ) -> str:
        """根据模式构建 system prompt。"""
        if not is_sub_agent:
            return agent_system_prompt

        from src.subagent.sub_agent_orchestrator import SubAgentOrchestrator
        orchestrator = SubAgentOrchestrator()
        return orchestrator.build_sub_agent_system_prompt(
            parent_system_prompt=parent_system_prompt or "",
            description=sub_agent_description or "",
        )

    def _build_tool_registry(
        self,
        is_sub_agent: bool,
        allowed_tools: Optional[list[str]] = None,
    ) -> Optional[IToolRegistry]:
        """根据模式构建工具注册表。"""
        if not is_sub_agent:
            return self.tool_registry

        from src.subagent.sub_agent_orchestrator import SubAgentOrchestrator
        from src.infrastructure.tools.registry import ToolRegistry
        orchestrator = SubAgentOrchestrator()
        return orchestrator.create_sub_agent_tool_registry(
            self.tool_registry,
            registry_factory=lambda: ToolRegistry(),
            allowed_tools=allowed_tools,
        )

    def _build_event_emitter(
        self,
        is_sub_agent: bool,
        parent_task_id: Optional[str],
        sub_task_id: Optional[str],
    ) -> Optional[IEventEmitter]:
        """根据模式构建事件发射器。"""
        if not is_sub_agent:
            return self.event_emitter

        return ProxyEventEmitter(
            self.event_emitter,
            parent_task_id=parent_task_id or "",
            sub_task_id=sub_task_id or "",
        )

    @staticmethod
    def _build_initial_state(
        *,
        task: Task,
        messages: list,
        content: str,
        model: Optional[str],
        max_turns: int,
        workspace: str,
        system_prompt: str,
        is_sub_agent: bool,
        parent_task_id: Optional[str],
    ) -> dict:
        """构建 LangGraph 初始 AgentState。"""
        return {
            "messages": messages,
            "task_id": task.id,
            "workspace": workspace,
            "user_message": content,
            "task_start_message_count": len(messages),
            "model": model,
            "current_turn": 0,
            "max_turns": max_turns,
            "phase": "idle",
            "should_end": False,
            "is_complete": False,
            "pending_tool_calls": [],
            "tool_results": {},
            "awaiting_user_input": False,
            "last_executed_tool_call_ids": [],
            "loop_detection_count": 0,
            "loop_detected": False,
            "loop_type": None,
            "stuck_detection_count": 0,
            "stuck_detected": False,
            "current_llm_text": "",
            "empty_retry_count": 0,
            "system_prompt": system_prompt,
            "final_result": None,
            "error": None,
            "compression_strategy": None,
            "is_sub_agent": is_sub_agent,
            "parent_task_id": parent_task_id,
        }

    async def _load_history_fallback(self, session_id: str) -> list:
        """降级方案：无 PromptContextInterface 时的简单历史加载。"""
        messages: list = []
        history_messages = await self.message_repo.list_by_session(
            session_id, limit=20
        )
        for msg in history_messages:
            if msg.role == SessionMessageRole.USER:
                messages.append(HumanMessage(content=msg.content))
            elif msg.role == SessionMessageRole.ASSISTANT:
                content_parts = [msg.content or ""]
                if msg.tool_calls:
                    tool_names = list(dict.fromkeys(
                        tc.get("name", "") for tc in msg.tool_calls if tc.get("name")
                    ))
                    if tool_names:
                        tools_summary = f"\n\n[Used Tools: {', '.join(tool_names)}]"
                        content_parts.append(tools_summary)
                messages.append(
                    AIMessage(content="".join(content_parts)))
            elif msg.role == SessionMessageRole.TOOL_SUMMARY:
                messages.append(HumanMessage(
                    content=f"[Tool Results] {msg.content}"))
        return messages
