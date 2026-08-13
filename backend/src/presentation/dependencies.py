"""表现层 - 依赖注入配置

组合根(Composition Root): 在这里将所有依赖组装在一起
"""

from functools import lru_cache

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.agent_loop.stream_event import StreamEventService
from src.domain.repositories.task_repository import ITaskRepository
from src.domain.repositories.agent_repository import IAgentRepository
from src.domain.repositories.session_repository import ISessionRepository
from src.domain.repositories.session_message_repository import ISessionMessageRepository
from src.domain.skills import ISkillRepository
from src.domain.repositories.tool_registry import IToolRegistry
from src.domain.interfaces.llm_provider import ILLMProvider
from src.domain.interfaces.prompt_context_interface import PromptContextInterface
from src.infrastructure.agent.prompt_context_impl import PromptContextImpl
from src.infrastructure.llm.config import LLMSettings
from src.infrastructure.llm.llm_provider_impl import LLMProviderImpl
from src.infrastructure.repositories.sqlite_task_repo import SQLiteTaskRepository
from src.infrastructure.repositories.sqlite_agent_repo import SQLiteAgentRepository
from src.infrastructure.repositories.sqlite_session_repo import SQLiteSessionRepository
from src.infrastructure.repositories.sqlite_session_message_repo import (
    SQLiteSessionMessageRepository,
)
from src.infrastructure.skills import SQLiteSkillRepository
from src.application.skills.storage import SkillStorageService
from src.infrastructure.tools.registry import ToolRegistry
from src.application.skills.upload import SkillUploadService


# 异步数据库依赖
async def get_async_db() -> AsyncSession:
    """获取异步数据库 Session"""
    from src.infrastructure.database.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


def get_task_repository(
    db: AsyncSession = Depends(get_async_db),
) -> ITaskRepository:
    """获取任务仓储实例"""
    return SQLiteTaskRepository(db)


def get_agent_repository(
    db: AsyncSession = Depends(get_async_db),
) -> IAgentRepository:
    """获取 Agent 仓储实例"""
    return SQLiteAgentRepository(db)


def get_agent_use_case(
    db: AsyncSession = Depends(get_async_db),
):
    """获取 Agent 管理用例实例"""
    from src.application.agent import AgentManagementUseCase
    return AgentManagementUseCase(agent_repo=SQLiteAgentRepository(db))


def get_event_service() -> StreamEventService:
    """获取事件服务实例"""
    from src.application.services.session_file_storage import SessionFileStorage
    return StreamEventService(file_storage=SessionFileStorage())



def get_session_repository(
    db: AsyncSession = Depends(get_async_db),
) -> ISessionRepository:
    """获取会话仓储实例"""
    return SQLiteSessionRepository(db)


def get_session_message_repository(
    db: AsyncSession = Depends(get_async_db),
) -> ISessionMessageRepository:
    """获取会话消息仓储实例"""
    return SQLiteSessionMessageRepository(db)


def get_skill_repository(
    db: AsyncSession = Depends(get_async_db),
) -> ISkillRepository:
    """获取 Skill 仓储实例"""
    return SQLiteSkillRepository(db)


def get_skill_storage_service() -> SkillStorageService:
    """获取 Skill 存储服务实例"""
    return SkillStorageService()


def get_skill_upload_service(
    skill_repo: ISkillRepository = Depends(get_skill_repository),
    storage_service: SkillStorageService = Depends(get_skill_storage_service),
) -> SkillUploadService:
    """获取 Skill 上传服务实例"""
    return SkillUploadService(skill_repo, storage_service)


def get_prompt_context() -> PromptContextInterface:
    """获取 Prompt 上下文组装实现实例"""
    return PromptContextImpl()


# LLM 依赖注入
@lru_cache()
def get_llm_settings() -> LLMSettings:
    """获取 LLM 配置单例"""
    return LLMSettings()


def get_llm_provider() -> ILLMProvider:
    """获取 LLM Provider 实例"""
    return LLMProviderImpl()


# === 命令确认 依赖注入（进程级单例，见 design 决策 θ）===


@lru_cache()
def get_pending_approval_registry():
    """获取待审批注册表单例。

    顶层 / sub-agent / team 的 ConfirmationMiddleware 与 /approvals 端点
    共享同一实例——用于校验待确认调用存在性。
    """
    from src.infrastructure.tools.confirmation.store import get_default_registry

    return get_default_registry()


@lru_cache()
def get_session_approval_store():
    """获取会话许可存储单例（同上共享）。"""
    from src.infrastructure.tools.confirmation.store import get_default_session_store

    return get_default_session_store()


@lru_cache()
def get_graph_resume_manager():
    """获取图恢复管理器单例。

    agent_loop_runner 在 GraphInterrupt 时注册恢复上下文；
    /approvals 端点取回并执行 graph.ainvoke(Command(resume=decision))。
    """
    from src.infrastructure.agent.graph_resume_manager import (
        get_default_resume_manager,
    )

    return get_default_resume_manager()


# === Tool Registry 依赖注入 ===


def get_tool_registry() -> IToolRegistry:
    """获取工具注册表实例"""
    return create_tool_registry()


def create_tool_registry() -> IToolRegistry:
    """创建并配置工具注册表

    组装 ExecutionPipeline + 中间件 + 自动注册内置工具。
    """
    from src.infrastructure.tools.confirmation.pipeline import build_default_pipeline

    # 导入内置工具模块（触发 @tool 装饰器注册）
    import src.infrastructure.tools.builtin.web_search  # noqa: F401
    import src.infrastructure.tools.builtin.web_fetch  # noqa: F401
    import src.infrastructure.tools.builtin.file_ops  # noqa: F401
    import src.infrastructure.tools.builtin.clarify  # noqa: F401
    import src.infrastructure.tools.builtin.task_create  # noqa: F401
    import src.infrastructure.tools.builtin.task_update  # noqa: F401
    import src.infrastructure.tools.builtin.shell  # noqa: F401
    import src.infrastructure.tools.builtin.session_spawn  # noqa: F401
    import src.infrastructure.tools.builtin.team_tools  # noqa: F401

    # 构建中间件管道（Confirmation 置于 Security 之前 = Timeout 之外）
    pipeline = build_default_pipeline()

    # 创建 Registry 并自动注册
    registry = ToolRegistry(pipeline=pipeline)
    registry.auto_register_collected()

    return registry


# === Memory 依赖注入 ===


def get_memory_repository(
    db: AsyncSession = Depends(get_async_db),
):
    """获取 Memory 仓储实例"""
    from src.infrastructure.memory import SQLiteMemoryRepository
    return SQLiteMemoryRepository(db)


def get_memory_use_case(
    db: AsyncSession = Depends(get_async_db),
):
    """获取 Memory 管理用例实例"""
    from src.application.memory.management import MemoryManagementUseCase
    from src.domain.memory.service import MemoryService
    from src.infrastructure.memory import SQLiteMemoryRepository

    repo = SQLiteMemoryRepository(db)
    service = MemoryService(repository=repo)
    return MemoryManagementUseCase(memory_repo=repo, memory_service=service)


# === SendMessageUseCase 构建工厂 ===


def get_send_message_use_case(request: Request):
    """构建 SendMessageUseCase — 后台任务使用独立 DB session 与完整依赖图。

    每次调用创建独立的 AsyncSession，供后台 Agent Loop 长期持有。
    所有仓储、应用服务、用例均在此组装，路由层无需了解具体实现。
    """
    from sqlalchemy.ext.asyncio import AsyncSession as SAAsyncSession

    from src.application.agent_loop.send_message import SendMessageUseCase
    from src.application.services.agent_loop_runner import AgentLoopRunner
    from src.application.services.session_title_generator import SessionTitleGenerator
    from src.application.services.task_completion_service import TaskCompletionService
    from src.infrastructure.database.session import async_engine
    from src.infrastructure.repositories.sqlite_task_repo import SQLiteTaskRepository
    from src.infrastructure.repositories.sqlite_agent_repo import SQLiteAgentRepository
    from src.infrastructure.repositories.sqlite_session_repo import SQLiteSessionRepository
    from src.infrastructure.repositories.sqlite_session_message_repo import (
        SQLiteSessionMessageRepository,
    )
    from src.infrastructure.skills import SQLiteSkillRepository
    from src.application.services.session_file_storage import SessionFileStorage

    bg_db = SAAsyncSession(async_engine)
    bg_task_repo = SQLiteTaskRepository(bg_db)
    bg_agent_repo = SQLiteAgentRepository(bg_db)
    bg_session_repo = SQLiteSessionRepository(bg_db)
    bg_message_repo = SQLiteSessionMessageRepository(bg_db)
    bg_skill_repo = SQLiteSkillRepository(bg_db)

    bg_event_emitter = request.app.state.event_service
    bg_tool_registry = create_tool_registry()
    bg_llm_provider = get_llm_provider()
    bg_llm_settings = get_llm_settings()
    bg_prompt_context = get_prompt_context()
    bg_file_storage = SessionFileStorage()

    title_generator = SessionTitleGenerator(
        llm_provider=bg_llm_provider,
        session_repo=bg_session_repo,
    )
    completion_service = TaskCompletionService(
        message_repo=bg_message_repo,
        task_repo=bg_task_repo,
        session_repo=bg_session_repo,
        file_storage=bg_file_storage,
    )
    loop_runner = AgentLoopRunner(
        agent_repo=bg_agent_repo,
        llm_provider=bg_llm_provider,
        prompt_context=bg_prompt_context,
        message_repo=bg_message_repo,
        skill_repo=bg_skill_repo,
        task_repo=bg_task_repo,
        session_repo=bg_session_repo,
        event_emitter=bg_event_emitter,
        tool_registry=bg_tool_registry,
        workflow_builder=None,
        task_completion_service=completion_service,
        default_model=bg_llm_settings.default_model,
        file_storage=bg_file_storage,
    )

    return SendMessageUseCase(
        session_repo=bg_session_repo,
        message_repo=bg_message_repo,
        task_repo=bg_task_repo,
        event_emitter=bg_event_emitter,
        tool_registry=bg_tool_registry,
        loop_runner=loop_runner,
        title_generator=title_generator,
        default_model=bg_llm_settings.default_model,
        running_tasks=request.app.state.running_tasks,
        file_storage=bg_file_storage,
    )


# === TaskManagementUseCase 依赖注入 ===


def get_task_management_use_case(
    db: AsyncSession = Depends(get_async_db),
    request: Request = None,
):
    """获取 Task 管理用例实例"""
    from src.application.tasks.management import TaskManagementUseCase
    from src.infrastructure.agent.graph_resume_manager import get_default_resume_manager
    from src.infrastructure.repositories.sqlite_task_repo import SQLiteTaskRepository
    from src.infrastructure.repositories.sqlite_agent_repo import SQLiteAgentRepository
    from src.infrastructure.tools.confirmation.store import get_default_registry

    task_repo = SQLiteTaskRepository(db)
    agent_repo = SQLiteAgentRepository(db)

    running_tasks = {}
    event_emitter = None
    if request is not None:
        running_tasks = getattr(request.app.state, "running_tasks", {})
        event_emitter = getattr(request.app.state, "event_service", None)

    return TaskManagementUseCase(
        task_repo=task_repo,
        agent_repo=agent_repo,
        running_tasks=running_tasks,
        event_emitter=event_emitter,
        resume_manager=get_default_resume_manager(),
        approval_registry=get_default_registry(),
    )


# === SkillManagementUseCase 依赖注入 ===


def get_skill_management_use_case(
    db: AsyncSession = Depends(get_async_db),
):
    """获取 Skill 管理用例实例"""
    from src.application.skills.management import SkillManagementUseCase

    return SkillManagementUseCase(skill_repo=SQLiteSkillRepository(db))


# === Team 依赖注入 ===


def get_team_repository(
    db: AsyncSession = Depends(get_async_db),
):
    """获取 Team 仓储实例"""
    from src.infrastructure.repositories.sqlite_team_repo import SQLiteTeamRepository
    return SQLiteTeamRepository(db)


def get_team_management_use_case(
    db: AsyncSession = Depends(get_async_db),
):
    """获取 Team 管理用例实例"""
    from src.application.team.management import TeamManagementUseCase
    from src.infrastructure.repositories.sqlite_team_repo import SQLiteTeamRepository
    from src.infrastructure.repositories.sqlite_agent_repo import SQLiteAgentRepository

    return TeamManagementUseCase(
        team_repo=SQLiteTeamRepository(db),
        agent_repo=SQLiteAgentRepository(db),
    )


def get_team_execution_use_case(request: Request):
    """构建 TeamExecutionUseCase — 每次调用创建独立的依赖图。

    与 get_send_message_use_case 类似，使用独立 DB session 与完整依赖图。
    """
    from sqlalchemy.ext.asyncio import AsyncSession as SAAsyncSession

    from src.application.team.execution import TeamExecutionUseCase
    from src.infrastructure.database.session import async_engine
    from src.infrastructure.repositories.sqlite_team_repo import SQLiteTeamRepository
    from src.infrastructure.repositories.sqlite_agent_repo import SQLiteAgentRepository
    from src.infrastructure.repositories.sqlite_task_repo import SQLiteTaskRepository
    from src.infrastructure.repositories.sqlite_session_repo import SQLiteSessionRepository
    from src.infrastructure.repositories.sqlite_session_message_repo import (
        SQLiteSessionMessageRepository,
    )

    bg_db = SAAsyncSession(async_engine)
    bg_team_repo = SQLiteTeamRepository(bg_db)
    bg_agent_repo = SQLiteAgentRepository(bg_db)
    bg_task_repo = SQLiteTaskRepository(bg_db)
    bg_session_repo = SQLiteSessionRepository(bg_db)
    bg_message_repo = SQLiteSessionMessageRepository(bg_db)

    bg_event_emitter = request.app.state.event_service
    bg_tool_registry = create_tool_registry()
    bg_llm_provider = get_llm_provider()
    bg_llm_settings = get_llm_settings()

    return TeamExecutionUseCase(
        team_repo=bg_team_repo,
        agent_repo=bg_agent_repo,
        task_repo=bg_task_repo,
        session_repo=bg_session_repo,
        message_repo=bg_message_repo,
        tool_registry=bg_tool_registry,
        llm_provider=bg_llm_provider,
        event_emitter=bg_event_emitter,
        loop_runner_factory=None,  # 使用内部 fallback 创建
        default_model=bg_llm_settings.default_model,
    )
