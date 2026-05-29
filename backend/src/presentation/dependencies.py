"""表现层 - 依赖注入配置

组合根(Composition Root): 在这里将所有依赖组装在一起
"""

from contextlib import asynccontextmanager
from functools import lru_cache

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.use_cases.stream_event import StreamEventService
from src.domain.repositories.event_repository import IEventRepository
from src.domain.repositories.task_repository import ITaskRepository
from src.domain.repositories.agent_repository import IAgentRepository
from src.domain.repositories.session_repository import ISessionRepository
from src.domain.repositories.session_message_repository import ISessionMessageRepository
from src.skills.skill_repository import ISkillRepository
from src.domain.repositories.tool_registry import IToolRegistry
from src.domain.interfaces.llm_provider import ILLMProvider
from src.infrastructure.llm.config import LLMSettings
from src.infrastructure.llm.llm_provider_impl import LLMProviderImpl
from src.infrastructure.repositories.sqlite_event_repo import SQLiteEventRepository
from src.infrastructure.repositories.sqlite_task_repo import SQLiteTaskRepository
from src.infrastructure.repositories.sqlite_agent_repo import SQLiteAgentRepository
from src.infrastructure.repositories.sqlite_session_repo import SQLiteSessionRepository
from src.infrastructure.repositories.sqlite_session_message_repo import (
    SQLiteSessionMessageRepository,
)
from src.infrastructure.repositories.sqlite_skill_repo import SQLiteSkillRepository
from src.application.services.skill_storage_service import SkillStorageService
from src.infrastructure.tools.registry import ToolRegistry
from src.application.use_cases.skill_upload import SkillUploadService


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


def get_event_repository(
    db: AsyncSession = Depends(get_async_db),
) -> IEventRepository:
    """获取事件仓储实例"""
    return SQLiteEventRepository(db)


def get_agent_repository(
    db: AsyncSession = Depends(get_async_db),
) -> IAgentRepository:
    """获取 Agent 仓储实例"""
    return SQLiteAgentRepository(db)


def get_event_service() -> StreamEventService:
    """获取事件服务实例"""
    return StreamEventService(create_event_repo_factory())


def create_event_repo_factory():
    """创建供 StreamEventService 使用的短生命周期事件仓储工厂。"""
    from src.infrastructure.database.session import AsyncSessionLocal

    @asynccontextmanager
    async def _factory():
        async with AsyncSessionLocal() as session:
            yield SQLiteEventRepository(session)

    return _factory


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


# LLM 依赖注入
@lru_cache()
def get_llm_settings() -> LLMSettings:
    """获取 LLM 配置单例"""
    return LLMSettings()


def get_llm_provider() -> ILLMProvider:
    """获取 LLM Provider 实例"""
    return LLMProviderImpl()


# === Tool Registry 依赖注入 ===


def get_tool_registry() -> IToolRegistry:
    """获取工具注册表实例"""
    return create_tool_registry()


def create_tool_registry() -> IToolRegistry:
    """创建并配置工具注册表

    组装 ExecutionPipeline + 中间件 + 自动注册内置工具。
    """
    from src.infrastructure.tools.pipeline import ExecutionPipeline
    from src.infrastructure.tools.middleware.security import SecurityMiddleware
    from src.infrastructure.tools.middleware.rate_limit import RateLimitMiddleware
    from src.infrastructure.tools.middleware.timeout import TimeoutMiddleware
    from src.infrastructure.tools.middleware.sandbox import SandboxMiddleware

    # 导入内置工具模块（触发 @tool 装饰器注册）
    import src.infrastructure.tools.builtin.web_search  # noqa: F401
    import src.infrastructure.tools.builtin.web_fetch  # noqa: F401
    import src.infrastructure.tools.builtin.file_ops  # noqa: F401
    import src.infrastructure.tools.builtin.clarify  # noqa: F401
    import src.infrastructure.tools.builtin.task_create  # noqa: F401
    import src.infrastructure.tools.builtin.task_update  # noqa: F401
    import src.infrastructure.tools.builtin.shell  # noqa: F401
    import src.infrastructure.tools.builtin.session_spawn  # noqa: F401

    # 构建中间件管道
    pipeline = ExecutionPipeline()
    pipeline.add_middleware(SecurityMiddleware(allowed_tools=None))
    pipeline.add_middleware(RateLimitMiddleware(global_max_per_minute=300))
    pipeline.add_middleware(TimeoutMiddleware())
    pipeline.add_middleware(SandboxMiddleware())

    # 创建 Registry 并自动注册
    registry = ToolRegistry(pipeline=pipeline)
    registry.auto_register_collected()

    return registry
