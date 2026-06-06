"""应用层 - Team 执行用例

编排团队执行流程：
- 加载团队和成员
- 创建消息总线
- 构建 leader 的 system prompt
- 启动 leader AgentLoopRunner（member 由 assign_team_task 工具同步执行）
- 协调 shutdown
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Optional

from src.domain.team.repository import ITeamRepository
from src.domain.team.values import TeamRole, TeamStatus
from src.domain.team.orchestrator import TeamOrchestrator
from src.domain.agent.repository import IAgentRepository
from src.domain.aggregates.task.task import Task, TaskConfig, TaskStatus
from src.domain.repositories.task_repository import ITaskRepository
from src.domain.repositories.session_repository import ISessionRepository
from src.domain.repositories.session_message_repository import ISessionMessageRepository
from src.domain.repositories.tool_registry import IToolRegistry
from src.domain.interfaces.llm_provider import ILLMProvider
from src.domain.services import IEventEmitter
from src.infrastructure.team import InProcessTeamMessageBus

logger = logging.getLogger(__name__)


class TeamExecutionUseCase:
    """Team 执行用例

    负责创建团队执行上下文、启动 leader 和 member agent loop、
    管理消息总线和生命周期。
    """

    def __init__(
        self,
        team_repo: ITeamRepository,
        agent_repo: IAgentRepository,
        task_repo: ITaskRepository,
        session_repo: ISessionRepository,
        message_repo: ISessionMessageRepository,
        tool_registry: IToolRegistry,
        llm_provider: ILLMProvider,
        event_emitter: IEventEmitter,
        loop_runner_factory: Any = None,  # AgentLoopRunner 工厂
        default_model: str = "gpt-4",
    ) -> None:
        self._team_repo = team_repo
        self._agent_repo = agent_repo
        self._task_repo = task_repo
        self._session_repo = session_repo
        self._message_repo = message_repo
        self._tool_registry = tool_registry
        self._llm_provider = llm_provider
        self._event_emitter = event_emitter
        self._loop_runner_factory = loop_runner_factory
        self._default_model = default_model

    async def execute(
        self,
        team_id: str,
        goal: str,
        session_id: Optional[str] = None,
        model: Optional[str] = None,
        max_turns: int = 100,
        workspace: str = "/tmp/team-workspace",
        execution_id: Optional[str] = None,
    ) -> dict:
        """执行团队目标

        Args:
            team_id: 团队 ID
            goal: 执行目标
            session_id: 会话 ID（可选，自动创建）
            model: LLM 模型
            max_turns: 最大轮次
            workspace: 工作目录
            execution_id: 预生成的 execution ID（同时也是 leader task_id）

        Returns:
            执行结果: { execution_id, team_id, status }
        """
        # 1. 加载团队和成员
        team = await self._team_repo.get_by_id(team_id)
        if team is None:
            raise ValueError(f"Team {team_id} not found")

        members = await self._team_repo.list_members(team_id)
        if not members:
            raise ValueError(f"Team {team_id} has no members")

        # 识别 leader 和 members
        leader_member = next(
            (m for m in members if m.role == TeamRole.LEADER), None)
        if leader_member is None:
            raise ValueError(f"Team {team_id} has no leader")

        regular_members = [m for m in members if m.role == TeamRole.MEMBER]
        if not regular_members:
            raise ValueError(f"Team {team_id} has no regular members")

        # 2. 加载 agent 名称与描述映射
        agent_names: dict[str, str] = {}
        agent_descriptions: dict[str, str] = {}
        for m in members:
            agent = await self._agent_repo.get_by_id(m.agent_id)
            if agent:
                agent_names[m.agent_id] = agent.name
                agent_descriptions[m.agent_id] = agent.description or ""

        # 3. 更新团队状态
        team.goal = goal
        team.status = TeamStatus.EXECUTING
        team.updated_at = datetime.now()
        await self._team_repo.update(team)

        # 4. 创建消息总线并注册所有 agent
        message_bus = InProcessTeamMessageBus()
        for m in members:
            await message_bus.register_agent(m.agent_id)

        # 5. 构建 prompt 注入
        orchestrator = TeamOrchestrator()
        leader_context = orchestrator.build_leader_prompt_additions(
            team, members, agent_names, agent_descriptions,
        )

        # 6. 创建 leader task（使用预生成的 execution_id）
        if execution_id is None:
            execution_id = f"team-{uuid.uuid4().hex[:12]}"
        model = model or self._default_model

        leader_task = Task(
            id=execution_id,
            message=goal,
            workspace=workspace,
            status=TaskStatus.RUNNING,
            model=model,
            config=TaskConfig(max_turns=max_turns),
            max_turns=max_turns,
            agent_id=leader_member.agent_id,
            session_id=session_id or execution_id,
            started_at=datetime.now(),
        )

        # 持久化 leader task（TaskCompletionService 需要从 DB 更新）
        if self._task_repo:
            leader_task = await self._task_repo.add(leader_task)

        # 7. 发射 team:execution:started 事件
        if self._event_emitter:
            try:
                await self._event_emitter.emit(
                    execution_id,
                    "team:execution:started",
                    {
                        "team_id": team_id,
                        "team_name": team.name,
                        "goal": goal,
                        "leader_agent_id": leader_member.agent_id,
                        "member_count": len(regular_members),
                        "member_agent_ids": [
                            m.agent_id for m in regular_members],
                    },
                )
            except Exception:
                logger.warning("Failed to emit team:execution:started event",
                               exc_info=True)

        # 8. 启动 leader AgentLoopRunner
        try:
            loop_runner = self._get_loop_runner()
            leader_coro = loop_runner.run(
                agent_id=leader_member.agent_id,
                session_id=leader_task.session_id,
                task=leader_task,
                content=goal,
                model=model,
                max_turns=max_turns,
                workspace=workspace,
                team_mode=True,
                team_id=team_id,
                team_role="leader",
                team_message_bus=message_bus,
                team_context=leader_context,
                leader_agent_id=leader_member.agent_id,
                persist_session_messages=False,
            )

            # 9. 等待 leader 完成（member 由 assign_team_task 工具同步执行）
            await leader_coro

            # 10. 关闭消息总线
            await message_bus.shutdown()

            # 11. 更新团队状态
            leader_task_result = await self._task_repo.get_by_id(
                execution_id) if self._task_repo else None
            if leader_task_result and leader_task_result.status == TaskStatus.FAILED:
                team.status = TeamStatus.FAILED
            else:
                team.status = TeamStatus.COMPLETED
            team.updated_at = datetime.now()
            await self._team_repo.update(team)

            # 12. 发射 team:execution:completed 事件
            if self._event_emitter:
                try:
                    await self._event_emitter.emit(
                        execution_id,
                        "team:execution:completed",
                        {
                            "team_id": team_id,
                            "team_name": team.name,
                            "status": team.status.value,
                            "result": leader_task_result.result if leader_task_result else "",
                        },
                    )
                except Exception:
                    logger.warning(
                        "Failed to emit team:execution:completed event", exc_info=True)

            return {
                "execution_id": execution_id,
                "team_id": team_id,
                "status": team.status.value,
                "result": leader_task_result.result if leader_task_result else "",
            }

        except Exception as e:
            logger.exception("Team execution failed: %s", e)
            team.status = TeamStatus.FAILED
            team.updated_at = datetime.now()
            await self._team_repo.update(team)

            if self._event_emitter:
                try:
                    await self._event_emitter.emit(
                        execution_id,
                        "team:execution:failed",
                        {"team_id": team_id, "error": str(e)},
                    )
                except Exception:
                    pass

            await message_bus.shutdown()
            raise

    def _get_loop_runner(self, fresh_db_session=None):
        """获取 AgentLoopRunner 实例

        Args:
            fresh_db_session: 可选的独立 DB session（用于 member runner 隔离）
        """
        if self._loop_runner_factory:
            return self._loop_runner_factory()
        # Fallback: create from dependencies
        from src.application.services.agent_loop_runner import AgentLoopRunner
        from src.application.services.task_completion_service import TaskCompletionService
        from src.infrastructure.agent.prompt_context_impl import PromptContextImpl
        from src.infrastructure.repositories.sqlite_task_repo import SQLiteTaskRepository
        from src.infrastructure.repositories.sqlite_session_repo import SQLiteSessionRepository
        from src.infrastructure.repositories.sqlite_session_message_repo import (
            SQLiteSessionMessageRepository,
        )

        if fresh_db_session is not None:
            # Use isolated DB session for member runners
            task_repo = SQLiteTaskRepository(fresh_db_session)
            session_repo = SQLiteSessionRepository(fresh_db_session)
            message_repo = SQLiteSessionMessageRepository(fresh_db_session)
        else:
            task_repo = self._task_repo
            session_repo = self._session_repo
            message_repo = self._message_repo

        completion_service = TaskCompletionService(
            message_repo=message_repo,
            task_repo=task_repo,
            session_repo=session_repo,
        )
        return AgentLoopRunner(
            agent_repo=self._agent_repo,
            llm_provider=self._llm_provider,
            prompt_context=PromptContextImpl(),
            message_repo=message_repo,
            skill_repo=None,
            task_repo=task_repo,
            session_repo=session_repo,
            event_emitter=self._event_emitter,
            tool_registry=self._tool_registry,
            workflow_builder=None,
            task_completion_service=completion_service,
            default_model=self._default_model,
        )
