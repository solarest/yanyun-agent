"""应用层 - Agent Loop 上下文构建器

封装 graph 执行前所有依赖的构建：LLM / ToolRegistry / EventEmitter /
InitialState / GraphConfig。
组合 SystemPromptBuilder 和 HistoryLoader 子组件。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

from src.domain.aggregates.agent.state_groups import (
    ContextFields,
    ControlFields,
    TaskFields,
    ToolFields,
)
from src.domain.services.token_utils import count_tokens, resolve_max_context_tokens
from src.infrastructure.adapters.langchain_adapter import LangChainAdapter
from src.infrastructure.tools.confirmation.pipeline import build_default_pipeline

if TYPE_CHECKING:
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
    from src.domain.services import IEventEmitter
    from src.domain.skills import ISkillRepository

logger = logging.getLogger(__name__)


def _lazy_sub_agent_runtime_scope():
    """延迟导入 sub_agent_runtime_scope 以避免循环依赖。"""
    from src.application.tools.sub_agent_runtime import sub_agent_runtime_scope
    return sub_agent_runtime_scope


class AgentLoopContext:
    """Agent Loop 依赖构建器

    在 graph 执行前构建所有需要的依赖：
    - System Prompt (via SystemPromptBuilder)
    - 历史消息 (via HistoryLoader)
    - LLM 实例 + 工具绑定
    - Tool Registry（主 agent / sub-agent / team mode）
    - Event Emitter（主 agent / sub-agent proxy）
    - 初始 AgentState
    - Graph Config
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
        default_model: str = "gpt-4",
    ):
        self._agent_repo = agent_repo
        self._llm_provider = llm_provider
        self._message_repo = message_repo
        self._skill_repo = skill_repo
        self._task_repo = task_repo
        self._session_repo = session_repo
        self._event_emitter = event_emitter
        self._tool_registry = tool_registry
        self._workflow_builder = workflow_builder
        self._default_model = default_model

        # 子组件
        from src.application.services.system_prompt_builder import SystemPromptBuilder
        from src.application.services.history_loader import HistoryLoader

        self._prompt_builder = SystemPromptBuilder(
            agent_repo=agent_repo,
            tool_registry=tool_registry,
            skill_repo=skill_repo,
        )
        self._history_loader = HistoryLoader(
            message_repo=message_repo,
            prompt_context=prompt_context,
        )

    async def build_all(
        self,
        *,
        agent_id: str,
        session_id: str,
        task: Any,  # Task
        content: str,
        model: Optional[str],
        max_turns: int,
        workspace: str,
        skill_ids: Optional[list[str]] = None,
        is_sub_agent: bool = False,
        parent_task_id: Optional[str] = None,
        sub_agent_description: Optional[str] = None,
        parent_system_prompt: Optional[str] = None,
        allowed_tools: Optional[list[str]] = None,
        send_message_use_case: Any = None,
        team_mode: bool = False,
        team_id: Optional[str] = None,
        team_role: Optional[str] = None,
        team_message_bus: Any = None,
        team_context: Optional[str] = None,
        leader_agent_id: Optional[str] = None,
        task_dir: Optional[str] = None,
    ) -> tuple[Any, dict, dict]:
        """构建 graph 执行所需的一切

        Returns:
            (graph, config, initial_state)
        """
        if model is None:
            model = self._default_model

        # Step A: Build event emitter
        effective_event_emitter = self._build_event_emitter(
            is_sub_agent=is_sub_agent,
            parent_task_id=parent_task_id,
            sub_task_id=task.id,
        )

        # Step B: Build system prompt
        system_prompt = await self._prompt_builder.build(
            agent_id=agent_id,
            workspace=workspace,
            skill_ids=skill_ids,
            team_context=team_context,
            is_sub_agent=is_sub_agent,
            parent_system_prompt=parent_system_prompt,
            sub_agent_description=sub_agent_description,
            team_mode=team_mode,
        )

        # Step C: Load history
        messages = await self._history_loader.load(
            session_id=session_id,
            system_prompt=system_prompt,
            model=model,
            content=content,
            is_sub_agent=is_sub_agent,
            team_mode=team_mode,
            team_role=team_role,
            default_model=self._default_model,
        )

        # Step D: Build tool registry
        effective_tool_registry = self._build_tool_registry(
            is_sub_agent=is_sub_agent,
            allowed_tools=allowed_tools,
            team_mode=team_mode,
            team_role=team_role,
        )

        # Step E: Build LLM
        llm = self._build_llm(model, effective_tool_registry, agent_id)

        # Step F: Build initial state
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

        # Step G: Build graph
        if self._workflow_builder:
            graph = self._workflow_builder.build()
        else:
            from src.infrastructure.agent.workflow_builder import AgentWorkflowBuilder
            graph = AgentWorkflowBuilder.build()

        # Step H: Build graph config
        from src.domain.interfaces.llm_error_handler import LLMErrorHandlerRegistry
        from src.infrastructure.agent.error_handlers import (
            ContextLimitErrorHandler,
            DefaultErrorHandler,
            TimeoutErrorHandler,
        )

        graph_config = {
            "configurable": {
                "thread_id": task.id,
                "llm": llm,
                "event_emitter": effective_event_emitter,
                "event_service": effective_event_emitter,
                "tool_registry": effective_tool_registry,
                "agent_id": agent_id,
                "llm_model": model,
                "session_id": session_id,
                "llm_error_handlers": LLMErrorHandlerRegistry([
                    ContextLimitErrorHandler(),
                    TimeoutErrorHandler(timeout_sec=300),
                    DefaultErrorHandler(),
                ]),
                "send_message_use_case": send_message_use_case or self,
                "sub_agent_runtime_scope": _lazy_sub_agent_runtime_scope(),
                "task_repo": self._task_repo,
                "parent_state": initial_state,
                "parent_agent_id": agent_id,
                "parent_session_id": session_id,
                "parent_task_id": parent_task_id or task.id,
                "team_mode": team_mode,
                "team_id": team_id,
                "team_role": team_role,
                "team_message_bus": team_message_bus,
                "leader_agent_id": leader_agent_id or "",
            }
        }

        return graph, graph_config, initial_state

    # ── Internal builders ──────────────────────────────────────

    def _build_llm(
        self,
        model: Optional[str],
        tool_registry: Optional[IToolRegistry],
        agent_id: str,
    ):
        llm = self._llm_provider.create_chat_model(
            model=model or None) if self._llm_provider else None
        if llm is None:
            raise RuntimeError("LLM Provider is not configured")

        if tool_registry and tool_registry.tool_count > 0:
            tool_schemas = LangChainAdapter.tool_defs_to_openai_functions(tool_registry)
            llm = llm.bind_tools(tool_schemas)
            logger.info("binding-tools agent %s Tool schemas: %s",
                        agent_id, tool_schemas)
        return llm

    def _build_tool_registry(
        self,
        is_sub_agent: bool,
        allowed_tools: Optional[list[str]] = None,
        team_mode: bool = False,
        team_role: Optional[str] = None,
    ) -> Optional[IToolRegistry]:
        from src.infrastructure.tools.registry import ToolRegistry

        if team_mode:
            registry = ToolRegistry(pipeline=build_default_pipeline())
            if team_role == "leader":
                LEADER_ALLOWED_TOOLS = frozenset({
                    "update_team_tasks",
                    "assign_team_task",
                    "file_read",
                    "file_search",
                    "file_grep",
                    "clarify",
                })
                for tool in self._tool_registry.list_tools():
                    if tool.name in LEADER_ALLOWED_TOOLS:
                        registry.register(tool)
            elif team_role == "member":
                for tool in self._tool_registry.list_tools():
                    if tool.name in ("update_team_tasks", "assign_team_task",
                                     "check_team_reports"):
                        continue
                    registry.register(tool)
            else:
                for tool in self._tool_registry.list_tools():
                    registry.register(tool)
            return registry

        if not is_sub_agent:
            return self._tool_registry

        from src.domain.services.sub_agent_orchestrator import SubAgentOrchestrator
        orchestrator = SubAgentOrchestrator()
        return orchestrator.create_sub_agent_tool_registry(
            self._tool_registry,
            registry_factory=lambda: ToolRegistry(pipeline=build_default_pipeline()),
            allowed_tools=allowed_tools,
        )

    def _build_event_emitter(
        self,
        is_sub_agent: bool,
        parent_task_id: Optional[str],
        sub_task_id: Optional[str],
    ) -> Optional[IEventEmitter]:
        if not is_sub_agent:
            return self._event_emitter

        from src.domain.services import ProxyEventEmitter
        return ProxyEventEmitter(
            self._event_emitter,
            parent_task_id=parent_task_id or "",
            sub_task_id=sub_task_id or "",
        )

    @staticmethod
    def _build_initial_state(
        *,
        task: Any,
        messages: list,
        content: str,
        model: Optional[str],
        max_turns: int,
        workspace: str,
        system_prompt: str,
        is_sub_agent: bool,
        parent_task_id: Optional[str],
    ) -> dict:
        max_context_tokens = resolve_max_context_tokens(model or "")
        initial_estimate = sum(
            count_tokens(str(msg)) for msg in messages
        )
        return {
            "messages": messages,
            "current_llm_text": "",
            "thinking_text": "",
            "error": None,
            "final_result": None,
            # ── Grouped accessors: per spec, use dataclasses for structured state ──
            **TaskFields(
                task_id=task.id,
                workspace=workspace,
                user_message=content,
                task_start_message_count=len(messages),
                model=model or "",
                system_prompt=system_prompt,
                is_sub_agent=is_sub_agent,
                parent_task_id=parent_task_id,
            ).to_update(),
            **ControlFields(
                current_turn=0,
                max_turns=max_turns,
                phase="idle",
                should_end=False,
                is_complete=False,
            ).to_update(),
            **ContextFields(
                max_tokens=max_context_tokens,
                estimate=initial_estimate,
                baseline=None,
                baseline_count=len(messages),
                compaction_attempts=0,
                emergency_requested=False,
                last_strategy=None,
            ).to_update(),
            **ToolFields(
                pending=[],
                results={},
                awaiting_input=False,
                last_executed_ids=[],
                final_result=None,
            ).to_update(),
            "pending_confirmation": None,
        }
