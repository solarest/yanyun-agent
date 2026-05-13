"""应用层用例 - Sub-Agent 启动器

职责：
- 同步阻塞模式启动 sub-agent
- 管理 sub-agent 生命周期和 SSE 事件转发
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from src.domain.entities.agent_state import AgentState
from src.domain.entities.task import Task, TaskConfig, TaskStatus
from src.domain.repositories.task_repository import ITaskRepository
from src.domain.services import IEventEmitter
from src.domain.repositories.tool_registry import IToolRegistry
from src.domain.services.sub_agent_orchestrator import SubAgentOrchestrator
from src.application.use_cases.agent_workflow import AgentWorkflowBuilder

logger = logging.getLogger(__name__)


class ProxyEventEmitter(IEventEmitter):
    """代理事件发射器 - 用于 sync 模式下转发 sub-agent 事件到父 stream

    将所有事件转发到父 event_emitter，并在 payload 中自动添加 sub_task_id 字段。
    """

    def __init__(self, parent_emitter: IEventEmitter, sub_task_id: str):
        self._parent_emitter = parent_emitter
        self._sub_task_id = sub_task_id

    async def emit(self, task_id: str, event_type: str, payload: dict[str, Any]) -> None:
        """转发事件到父 stream，添加 sub_task_id"""
        payload = {**payload, "sub_task_id": self._sub_task_id}
        await self._parent_emitter.emit(self._sub_task_id, event_type, payload)

    async def emit_phase_changed(
        self,
        task_id: str,
        new_phase: str,
        previous_phase: str,
        turn: int,
    ) -> None:
        """转发阶段变更事件"""
        await self._parent_emitter.emit(
            self._sub_task_id,
            "phase:changed",
            {
                "phase": new_phase,
                "previousPhase": previous_phase,
                "turn": turn,
                "sub_task_id": self._sub_task_id,
            },
        )

    async def emit_llm_chunk(
        self,
        task_id: str,
        turn: int,
        text: str,
    ) -> None:
        """转发 LLM 流式片段"""
        await self._parent_emitter.emit(
            self._sub_task_id,
            "llm:chunk",
            {
                "turn": turn,
                "text": text,
                "delta": True,
                "sub_task_id": self._sub_task_id,
            },
        )

    async def emit_thinking_chunk(
        self,
        task_id: str,
        turn: int,
        text: str,
    ) -> None:
        """转发深度思考片段"""
        await self._parent_emitter.emit(
            self._sub_task_id,
            "thinking:chunk",
            {
                "turn": turn,
                "text": text,
                "delta": True,
                "sub_task_id": self._sub_task_id,
            },
        )


class SubAgentLauncher:
    """Sub-Agent 启动器应用层用例

    负责创建、启动和管理 sub-agent 的生命周期。
    """

    def __init__(
        self,
        *,
        task_repo: ITaskRepository,
        event_emitter: IEventEmitter,
        tool_registry: IToolRegistry,
        orchestrator: SubAgentOrchestrator,
        llm_builder: Any,  # 函数：(model, tool_registry, agent_id) -> llm
    ):
        self._task_repo = task_repo
        self._event_emitter = event_emitter
        self._tool_registry = tool_registry
        self._orchestrator = orchestrator
        self._llm_builder = llm_builder

    async def launch_sync(
        self,
        *,
        description: str,
        parent_state: AgentState,
        parent_agent_id: str,
        parent_session_id: str,
        parent_task_id: str,
        workspace: str,
        model: Optional[str] = None,
        max_turns: int = 50,
        allowed_tools: Optional[list[str]] = None,
        user_message: str = "",
    ) -> dict[str, Any]:
        """同步阻塞模式启动 sub-agent

        1. 创建 sub-task 实体
        2. 构建 sub-agent 初始状态
        3. 创建 sub-agent 工具注册表
        4. 直接执行 sub-agent（等待完成）
        5. sub-agent 的事件通过 ProxyEventEmitter 转发到父 stream
        6. 返回执行结果

        Args:
            description: sub-agent 的任务描述
            parent_state: 父 agent 的当前状态
            parent_agent_id: 父 agent ID
            parent_session_id: 父 session ID
            parent_task_id: 父 task ID
            workspace: 工作目录
            model: 模型名称
            max_turns: 最大轮次
            allowed_tools: 允许的工具列表
            user_message: 用户原始任务输入

        Returns:
            {"status": "completed", "result": str, "sub_task_id": str}
            或
            {"status": "failed", "error": str, "sub_task_id": str}
        """
        import uuid

        # 1. 创建 sub-task
        sub_task_id = f"sub-{uuid.uuid4().hex[:12]}"
        effective_model = model or parent_state.get("model", "gpt-4")

        sub_task = Task(
            id=sub_task_id,
            message=description,
            workspace=workspace,
            status=TaskStatus.RUNNING,
            model=effective_model,
            config=TaskConfig(max_turns=max_turns),
            max_turns=max_turns,
            agent_id=parent_agent_id,
            session_id=parent_session_id,
            started_at=datetime.now(),
        )
        await self._task_repo.add(sub_task)

        # 2. 构建 sub-agent system prompt
        parent_system_prompt = parent_state.get("system_prompt", "")
        sub_system_prompt = self._orchestrator.build_sub_agent_system_prompt(
            parent_system_prompt=parent_system_prompt,
            description=description,
        )

        # 3. 构建初始状态
        initial_state = self._orchestrator.build_sub_agent_initial_state(
            system_prompt=sub_system_prompt,
            user_message=user_message or description,
            description=description,
            task_id=sub_task_id,
            workspace=workspace,
            parent_task_id=parent_task_id,
            max_turns=max_turns,
            model=effective_model,
        )

        # 4. 创建 sub-agent 工具注册表
        sub_registry = self._orchestrator.create_sub_agent_tool_registry(
            self._tool_registry,
            allowed_tools=allowed_tools,
        )

        # 5. 发射 sub_agent:started 事件
        await self._event_emitter.emit(
            parent_task_id,
            "sub_agent:started",
            {
                "sub_task_id": sub_task_id,
                "description": description,
                "parent_task_id": parent_task_id,
            },
        )

        # 6. 执行 sub-agent（同步等待）
        try:
            result = await self._run_sub_agent_loop(
                task=sub_task,
                initial_state=initial_state,
                agent_id=parent_agent_id,
                session_id=parent_session_id,
                model=effective_model,
                tool_registry=sub_registry,
                parent_task_id=parent_task_id,
                use_proxy_emitter=True,
            )

            # 7. 提取结果
            final_result = result.get("final_result") or result.get("error", "No result")

            # 8. 发射 sub_agent:completed 事件
            await self._event_emitter.emit(
                parent_task_id,
                "sub_agent:completed",
                {
                    "sub_task_id": sub_task_id,
                    "result": final_result,
                    "parent_task_id": parent_task_id,
                },
            )

            return {
                "status": "completed",
                "result": final_result,
                "sub_task_id": sub_task_id,
            }

        except Exception as e:
            logger.exception("Sub-agent failed: sub_task_id=%s", sub_task_id)

            # 发射 sub_agent:failed 事件
            await self._event_emitter.emit(
                parent_task_id,
                "sub_agent:failed",
                {
                    "sub_task_id": sub_task_id,
                    "error": str(e),
                    "parent_task_id": parent_task_id,
                },
            )

            return {
                "status": "failed",
                "error": str(e),
                "sub_task_id": sub_task_id,
            }

    async def _run_sub_agent_loop(
        self,
        *,
        task: Task,
        initial_state: dict,
        agent_id: str,
        session_id: str,
        model: str,
        tool_registry: IToolRegistry,
        parent_task_id: str,
    ) -> dict[str, Any]:
        """执行 sub-agent 的 LangGraph 工作流

        与主 agent loop 类似，但使用 sub-agent 特定的配置。
        使用 ProxyEventEmitter 转发事件到父 stream。

        Args:
            task: sub-task 实体
            initial_state: 初始状态
            agent_id: agent ID
            session_id: session ID
            model: 模型名称
            tool_registry: sub-agent 工具注册表
            parent_task_id: 父 task ID

        Returns:
            最终的状态字典
        """
        # 1. 构建 LLM（绑定 sub-agent 工具）
        llm = self._llm_builder(model, tool_registry, agent_id)

        # 2. 构建图配置（使用代理事件发射器）
        event_emitter = ProxyEventEmitter(self._event_emitter, task.id)

        graph_config = {
            "configurable": {
                "llm": llm,
                "event_emitter": event_emitter,
                "event_service": event_emitter,
                "tool_registry": tool_registry,
                "agent_id": agent_id,
                "llm_model": model,
            }
        }

        # 3. 编译工作流
        graph = AgentWorkflowBuilder().build()

        # 4. 发射任务启动事件
        await event_emitter.emit(task.id, "task:started", {})

        # 5. 执行工作流
        try:
            result = await graph.ainvoke(initial_state, graph_config)

            # 6. 终态处理
            final_result = result.get("final_result")
            error = result.get("error")
            final_turn = result.get("current_turn", task.current_turn)
            previous_phase = result.get("phase", "thinking")

            # 更新 task 状态
            task.status = TaskStatus.FAILED if error else TaskStatus.COMPLETED
            task.current_turn = final_turn
            task.completed_at = datetime.now()
            task.result = final_result
            task.error = error
            await self._task_repo.update(task)

            # 发射阶段变更和任务完成事件
            await event_emitter.emit_phase_changed(
                task.id,
                "failed" if error else "complete",
                previous_phase,
                final_turn,
            )

            if error:
                await event_emitter.emit(task.id, "task:failed", {"error": error})
            else:
                await event_emitter.emit(task.id, "task:completed", {"result": final_result})

            return result

        except asyncio.CancelledError:
            logger.info("Sub-agent loop cancelled for task %s", task.id)
            task.status = TaskStatus.CANCELLED
            task.completed_at = datetime.now()
            task.error = "cancelled"
            await self._task_repo.update(task)
            await event_emitter.emit(task.id, "task:cancelled", {})
            raise
        except Exception as e:
            logger.exception("Sub-agent loop failed for task %s: %s", task.id, e)
            task.status = TaskStatus.FAILED
            task.completed_at = datetime.now()
            task.error = str(e)
            await self._task_repo.update(task)
            await event_emitter.emit(task.id, "task:failed", {"error": str(e)})
            raise
