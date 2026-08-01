"""应用层 - Sub-Agent 隔离运行时工厂

提供 sub-agent 执行所需的隔离运行时环境上下文管理器。
从 session_spawn 工具中提取出的组合逻辑，用于解决 DDD 分层违规：
基础设施层不应直接导入应用层用例和服务。
"""
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from src.application.agent_loop.send_message import SendMessageUseCase
from src.application.services.agent_loop_runner import AgentLoopRunner
from src.application.services.session_title_generator import SessionTitleGenerator
from src.application.services.task_completion_service import TaskCompletionService
from src.infrastructure.database.session import AsyncSessionLocal
from src.infrastructure.repositories.sqlite_agent_repo import SQLiteAgentRepository
from src.infrastructure.repositories.sqlite_session_repo import SQLiteSessionRepository
from src.infrastructure.repositories.sqlite_session_message_repo import (
    SQLiteSessionMessageRepository,
)
from src.infrastructure.skills import SQLiteSkillRepository
from src.infrastructure.repositories.sqlite_task_repo import SQLiteTaskRepository

logger = logging.getLogger(__name__)


def _is_sqlite_task_repo(task_repo: Any) -> bool:
    return task_repo.__class__.__name__ == "SQLiteTaskRepository"


def _can_build_isolated_use_case(send_message_use_case: Any) -> bool:
    required_attrs = (
        "session_repo",
        "message_repo",
        "task_repo",
        "event_emitter",
        "tool_registry",
        "loop_runner",
        "running_tasks",
    )
    if not all(hasattr(send_message_use_case, attr) for attr in required_attrs):
        return False
    lr = send_message_use_case.loop_runner
    return lr is not None and hasattr(lr, "llm_provider")


@asynccontextmanager
async def sub_agent_runtime_scope(
    send_message_use_case: Any,
    task_repo: Any,
) -> AsyncIterator[tuple[Any, Any]]:
    """为一次 sub-agent 运行提供隔离的仓储会话。

    多个 session_spawn 会并行执行；生产环境中的 SQLite/SQLAlchemy AsyncSession
    不能跨并发任务共享。测试中的 mock repo 保持原路径，避免引入数据库依赖。
    """
    if not (_is_sqlite_task_repo(task_repo) and _can_build_isolated_use_case(send_message_use_case)):
        yield send_message_use_case, task_repo
        return

    async with AsyncSessionLocal() as db_session:
        isolated_task_repo = SQLiteTaskRepository(db_session)
        isolated_agent_repo = SQLiteAgentRepository(db_session)
        isolated_session_repo = SQLiteSessionRepository(db_session)
        isolated_message_repo = SQLiteSessionMessageRepository(db_session)
        isolated_skill_repo = SQLiteSkillRepository(db_session)

        # 共享资源从父 use_case 获取
        shared_llm_provider = send_message_use_case.loop_runner.llm_provider
        shared_event_emitter = send_message_use_case.event_emitter
        shared_tool_registry = send_message_use_case.tool_registry
        shared_running_tasks = send_message_use_case.running_tasks

        # 共享资源
        shared_file_storage = getattr(send_message_use_case, '_file_storage', None)

        # 构建应用服务（isolated repos + shared singletons）
        title_generator = SessionTitleGenerator(
            llm_provider=shared_llm_provider,
            session_repo=isolated_session_repo,
        )
        completion_service = TaskCompletionService(
            message_repo=isolated_message_repo,
            task_repo=isolated_task_repo,
            session_repo=isolated_session_repo,
            file_storage=shared_file_storage,
        )
        loop_runner = AgentLoopRunner(
            agent_repo=isolated_agent_repo,
            llm_provider=shared_llm_provider,
            prompt_context=None,
            message_repo=isolated_message_repo,
            skill_repo=isolated_skill_repo,
            task_repo=isolated_task_repo,
            session_repo=isolated_session_repo,
            event_emitter=shared_event_emitter,
            tool_registry=shared_tool_registry,
            workflow_builder=None,
            task_completion_service=completion_service,
            default_model=send_message_use_case.default_model,
            file_storage=shared_file_storage,
        )

        isolated_use_case = SendMessageUseCase(
            session_repo=isolated_session_repo,
            message_repo=isolated_message_repo,
            task_repo=isolated_task_repo,
            event_emitter=shared_event_emitter,
            tool_registry=shared_tool_registry,
            loop_runner=loop_runner,
            title_generator=title_generator,
            running_tasks=shared_running_tasks,
            file_storage=shared_file_storage,
        )
        yield isolated_use_case, isolated_task_repo
