"""应用层 - SendMessage 用例

核心编排用例：用户发送消息 → 创建 Task → 异步启动 Agent Loop。
精简为 thin facade，将具体执行逻辑委托给各应用服务。
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from src.application.services.agent_loop_runner import AgentLoopRunner
from src.application.services.session_title_generator import SessionTitleGenerator
from src.domain.aggregates.session.session_message import (
    MessageStatus,
    SessionMessage,
    SessionMessageRole,
)
from src.domain.aggregates.task.task import Task, TaskConfig, TaskStatus
from src.domain.events.task_events import TaskCreated
from src.domain.repositories.event_publisher import IEventPublisher
from src.domain.repositories.session_message_repository import (
    ISessionMessageRepository,
)
from src.domain.repositories.session_repository import ISessionRepository
from src.domain.repositories.task_repository import ITaskRepository
from src.domain.repositories.tool_registry import IToolRegistry
from src.domain.services import IEventEmitter

logger = logging.getLogger(__name__)


class SendMessageUseCase:
    """发送消息用例 — 同步准备 + 异步启动 Agent Loop。

    职责边界：
    - 同步阶段：保存用户消息 → 更新 Session → 创建 Task → 发布 TaskCreated
    - 异步启动：委托 AgentLoopRunner 执行后台 Agent Loop
    - 标题生成：委托 SessionTitleGenerator 异步生成

    不负责：Agent Loop 执行过程、终态结果持久化（由 AgentLoopRunner
    及其内部的 TaskCompletionService 处理）。
    """

    def __init__(
        self,
        session_repo: ISessionRepository,
        message_repo: ISessionMessageRepository,
        task_repo: Optional[ITaskRepository] = None,
        event_emitter: Optional[IEventEmitter] = None,
        tool_registry: Optional[IToolRegistry] = None,
        event_publisher: Optional[IEventPublisher] = None,
        loop_runner: Optional[AgentLoopRunner] = None,
        title_generator: Optional[SessionTitleGenerator] = None,
        running_tasks: Optional[dict[str, asyncio.Task]] = None,
        default_model: str = "gpt-4",
    ):
        self.session_repo = session_repo
        self.message_repo = message_repo
        self.task_repo = task_repo
        self.event_emitter = event_emitter
        self.tool_registry = tool_registry
        self.event_publisher = event_publisher
        self.loop_runner = loop_runner
        self.title_generator = title_generator
        self.running_tasks = running_tasks if running_tasks is not None else {}
        self.default_model = default_model

    async def execute(
        self,
        agent_id: str,
        session_id: str,
        content: str,
        model: Optional[str] = None,
        max_turns: int = 100,
        workspace: str = "/tmp/agent-workspace",
        skill_ids: Optional[list[str]] = None,
        # Sub-agent 模式参数
        is_sub_agent: bool = False,
        parent_task_id: Optional[str] = None,
        sub_agent_description: Optional[str] = None,
        parent_system_prompt: Optional[str] = None,
        sub_task: Optional[Task] = None,
        allowed_tools: Optional[list[str]] = None,
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
            skill_ids: 选中的 Skill ID 列表
            is_sub_agent: 是否为 sub-agent 模式
            parent_task_id: 父 task ID（sub-agent 模式）
            sub_agent_description: sub-agent 任务描述（sub-agent 模式）
            parent_system_prompt: 父 agent 的 system prompt（sub-agent 模式）
            sub_task: sub-task 实体（sub-agent 模式）
            allowed_tools: 允许的工具列表（sub-agent 模式）

        Returns:
            {"user_message": SessionMessage, "task_id": str}
        """
        persist_session_messages = not is_sub_agent

        # 1. 保存用户消息。sub-agent 的中间对话不写入父 session，最终结果通过
        #    Task.result 和 session_spawn 的 ToolMessage 回到主 agent。
        user_msg: Optional[SessionMessage] = None
        if persist_session_messages:
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
                # 首条消息自动生成标题 - 使用 LLM 提炼
                if session.message_count == 1 and self.title_generator:
                    # 异步生成标题，不阻塞主流程
                    asyncio.create_task(
                        self.title_generator.generate(session_id, content)
                    )
                await self.session_repo.update(session)

        # 3. 创建 Task
        effective_model = model or self.default_model
        if sub_task is not None:
            task = sub_task
            task.status = TaskStatus.RUNNING
            task.started_at = task.started_at or datetime.now()
        else:
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
        if self.task_repo and sub_task is None:
            task = await self.task_repo.add(task)

        if self.event_publisher and not is_sub_agent:
            await self.event_publisher.publish(TaskCreated(
                task_id=task.id,
                agent_id=agent_id,
                session_id=session_id,
                model=effective_model,
            ))

        # 4. 启动后台 runner
        asyncio_task: asyncio.Task | None = None
        if self.event_emitter and self.tool_registry and self.loop_runner:
            asyncio_task = asyncio.create_task(
                self.loop_runner.run(
                    agent_id=agent_id,
                    session_id=session_id,
                    task=task,
                    content=content,
                    model=effective_model,
                    max_turns=max_turns,
                    workspace=workspace,
                    skill_ids=skill_ids or [],
                    is_sub_agent=is_sub_agent,
                    parent_task_id=parent_task_id,
                    sub_agent_description=sub_agent_description,
                    parent_system_prompt=parent_system_prompt,
                    allowed_tools=allowed_tools,
                    persist_session_messages=persist_session_messages,
                    send_message_use_case=self,
                )
            )
            self.running_tasks[task.id] = asyncio_task
            asyncio_task.add_done_callback(
                lambda t: logger.info("Agent loop task %s finished", task.id)
            )
            asyncio_task.add_done_callback(
                lambda _t: self.running_tasks.pop(task.id, None)
            )

        return {
            "user_message": user_msg,
            "task_id": task.id,
            "asyncio_task": asyncio_task if (self.event_emitter and self.tool_registry) else None,
        }
