"""应用层 - Agent Loop 运行器 (薄编排层)

编排 Agent Loop 的完整执行流程：
Context 构建 → Graph 执行 → Lifecycle 处理。
"""

import asyncio
import logging
from typing import Any, Optional

from langgraph.graph.message import add_messages

from pathlib import Path

from src.domain.entities.event_types import AgentEventType
from src.application.services.agent_loop_context import AgentLoopContext
from src.application.services.agent_loop_lifecycle import AgentLoopLifecycle
from src.domain.repositories.agent_repository import IAgentRepository
from src.domain.repositories.session_message_repository import (
    ISessionMessageRepository,
)
from src.application.services.task_completion_service import TaskCompletionService
from src.domain.services.checkpoint_serializer import (
    deserialize_agent_state,
    serialize_agent_state,
)

logger = logging.getLogger(__name__)


class AgentLoopRunner:
    """后台 Agent Loop 运行器（薄编排层）。

    职责：委托 Context 构建所有依赖 → graph.ainvoke() → Lifecycle 处理结果。
    支持主 agent 模式、sub-agent 模式和 team mode。
    """

    def __init__(
        self,
        agent_repo: IAgentRepository,
        llm_provider: Any,
        prompt_context: Any,
        message_repo: ISessionMessageRepository,
        skill_repo: Any,
        task_repo: Any,
        session_repo: Any,
        event_emitter: Any,
        tool_registry: Any,
        workflow_builder: Any,
        task_completion_service: TaskCompletionService,
        default_model: str = "gpt-4",
        file_storage=None,
    ):
        # 暴露 llm_provider：sub_agent_runtime_scope 以此判断能否构建隔离运行时
        self.llm_provider = llm_provider
        self._context = AgentLoopContext(
            agent_repo=agent_repo,
            llm_provider=llm_provider,
            prompt_context=prompt_context,
            message_repo=message_repo,
            skill_repo=skill_repo,
            task_repo=task_repo,
            session_repo=session_repo,
            event_emitter=event_emitter,
            tool_registry=tool_registry,
            workflow_builder=workflow_builder,
            default_model=default_model,
        )
        self._lifecycle = AgentLoopLifecycle(
            task_repo=task_repo,
            task_completion_service=task_completion_service,
        )
        self._file_storage = file_storage

    async def run(
        self,
        *,
        agent_id: str,
        session_id: str,
        task: Any,
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
        persist_session_messages: bool = True,
        send_message_use_case: Any = None,
        team_mode: bool = False,
        team_id: Optional[str] = None,
        team_role: Optional[str] = None,
        team_message_bus: Any = None,
        team_context: Optional[str] = None,
        leader_agent_id: Optional[str] = None,
        task_dir: Optional[str] = None,
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
            sub_agent_description: sub-agent 任务描述
            parent_system_prompt: 父 agent 的 system prompt
            allowed_tools: 允许的工具列表
            persist_session_messages: 是否持久化会话消息
            send_message_use_case: SendMessageUseCase 引用
            team_mode: 是否为 team mode
            team_id: 团队 ID
            team_role: 团队角色 ("leader" | "member")
            team_message_bus: 团队消息总线
            team_context: team mode prompt 注入内容
            leader_agent_id: Leader 的 Agent ID
        """
        # Step 1: 构建所有依赖
        graph, graph_config, initial_state = await self._context.build_all(
            agent_id=agent_id,
            session_id=session_id,
            task=task,
            content=content,
            model=model,
            max_turns=max_turns,
            workspace=workspace,
            skill_ids=skill_ids,
            is_sub_agent=is_sub_agent,
            parent_task_id=parent_task_id,
            sub_agent_description=sub_agent_description,
            parent_system_prompt=parent_system_prompt,
            allowed_tools=allowed_tools,
            send_message_use_case=send_message_use_case,
            team_mode=team_mode,
            team_id=team_id,
            team_role=team_role,
            team_message_bus=team_message_bus,
            team_context=team_context,
            leader_agent_id=leader_agent_id,
            task_dir=task_dir,
        )
        self._configure_snapshot_storage(graph_config, task_dir)

        # 从 config 中提取 event_emitter（build_all 已构建）
        effective_event_emitter = graph_config["configurable"]["event_emitter"]

        try:
            # Step 2: 执行 graph
            await effective_event_emitter.emit(task.id, AgentEventType.TASK_STARTED, {})
            result = await graph.ainvoke(initial_state, graph_config)

            # Save checkpoint after successful graph execution
            self._save_checkpoint(task.id, task_dir, result)

            if result.get("pending_confirmation"):
                await self._lifecycle.handle_awaiting_confirmation(task)
                return

            # Step 3: 正常完成
            await self._lifecycle.handle_normal_completion(
                task=task,
                session_id=session_id,
                result=result,
                event_emitter=effective_event_emitter,
                persist_session_messages=persist_session_messages,
                task_dir=task_dir,
            )

        except asyncio.CancelledError:
            await self._lifecycle.handle_cancellation(
                task=task,
                event_emitter=effective_event_emitter,
            )

        except Exception as e:
            await self._lifecycle.handle_failure(
                task=task,
                error=e,
                event_emitter=effective_event_emitter,
            )

    async def resume_from_snapshot(
        self,
        *,
        task: Any,
        task_dir: Path,
        approval: dict[str, str] | None = None,
        send_message_use_case: Any = None,
    ) -> bool:
        """Continue a task from a task-local AgentState snapshot."""
        if self._file_storage is None:
            return False
        checkpoint = self._file_storage.read_latest_checkpoint(task_dir)
        if checkpoint is None:
            return False

        state = deserialize_agent_state(checkpoint["state"])
        pending = checkpoint.get("pending_confirmation")
        if pending and (
            not approval or approval.get("tool_call_id") != pending.get("tool_call_id")
        ):
            return False

        graph, graph_config, _ = await self._context.build_all(
            agent_id=task.agent_id,
            session_id=task.session_id,
            task=task,
            content=task.message,
            model=task.model,
            max_turns=task.max_turns,
            workspace=task.workspace,
            send_message_use_case=send_message_use_case,
            task_dir=str(task_dir),
        )
        self._configure_snapshot_storage(graph_config, str(task_dir))
        if approval:
            graph_config["configurable"]["approval"] = approval

            from src.infrastructure.agent.nodes.tool_execute_node import tool_execute_node

            tool_update = await tool_execute_node(state, graph_config)
            state = self._apply_state_update(state, tool_update)
            self._save_checkpoint(task.id, str(task_dir), state)
            if state.get("pending_confirmation"):
                await self._lifecycle.handle_awaiting_confirmation(task)
                return True

        result = await graph.ainvoke(state, graph_config)
        self._save_checkpoint(task.id, str(task_dir), result)
        event_emitter = graph_config["configurable"]["event_emitter"]
        if result.get("pending_confirmation"):
            await self._lifecycle.handle_awaiting_confirmation(task)
            return True
        await self._lifecycle.handle_normal_completion(
            task=task,
            session_id=task.session_id,
            result=result,
            event_emitter=event_emitter,
            task_dir=str(task_dir),
        )
        return True

    def _configure_snapshot_storage(
        self, graph_config: dict, task_dir: str | None
    ) -> None:
        """Expose the task-local storage boundary to graph persistence nodes."""
        configurable = graph_config.setdefault("configurable", {})
        configurable["file_storage"] = self._file_storage
        configurable["task_dir"] = task_dir

    @staticmethod
    def _apply_state_update(state: dict, update: dict) -> dict:
        """Apply the node update using the same message reducer as AgentState."""
        merged = {**state, **update}
        if "messages" in update:
            merged["messages"] = add_messages(state.get("messages", []), update["messages"])
        return merged

    def _save_checkpoint(self, task_id: str, task_dir: str | None, state: dict) -> None:
        """Save an AgentState checkpoint to file storage."""
        if not self._file_storage or not task_dir:
            return
        try:
            turn = state.get("current_turn", 0)
            serialized = serialize_agent_state(state)
            pending_confirmation = state.get("pending_confirmation")
            self._file_storage.write_checkpoint(
                Path(task_dir),
                serialized,
                turn_number=turn,
                resume_status=(
                    "awaiting_confirmation" if pending_confirmation else "running"
                ),
                pending_confirmation=pending_confirmation,
            )
        except Exception:
            logger.exception("Failed to save checkpoint for task %s", task_id)
