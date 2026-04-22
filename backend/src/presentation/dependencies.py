"""表现层 - 依赖注入配置

组合根(Composition Root): 在这里将所有依赖组装在一起
"""
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.base import Entity
from src.domain.repositories.base import Repository
from src.domain.repositories.task_repository import ITaskRepository
from src.domain.repositories.event_repository import IEventRepository
from src.infrastructure.repositories.in_memory_repo import InMemoryRepository
from src.infrastructure.repositories.sqlite_task_repo import SQLiteTaskRepository
from src.infrastructure.repositories.sqlite_event_repo import SQLiteEventRepository
from src.application.use_cases.ping_use_case import PingUseCase
from src.application.services.stream_event import StreamEventService


# 创建 Repository 实例(单例模式)
def get_repository() -> Repository[Entity]:
    """获取 Repository 实例"""
    return InMemoryRepository()


def get_ping_use_case(
    repository: Repository[Entity] = Depends(get_repository)
) -> PingUseCase:
    """获取 Ping UseCase 实例
    
    依赖注入链:
    PingUseCase -> Repository[Entity] -> InMemoryRepository
    """
    return PingUseCase(repository)


# 异步数据库依赖
async def get_async_db() -> AsyncSession:
    """获取异步数据库 Session"""
    from src.infrastructure.database.session import AsyncSession, async_engine
    from sqlalchemy.ext.asyncio import AsyncSession as SAAsyncSession
    
    async with SAAsyncSession(async_engine) as session:
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


def get_event_service(
    event_repo: IEventRepository = Depends(get_event_repository),
) -> StreamEventService:
    """获取事件服务实例"""
    return StreamEventService(event_repo)


# LLM 依赖注入
from functools import lru_cache
from src.infrastructure.llm.config import LLMSettings
from src.application.use_cases.create_llm_use_case import CreateLLMUseCase


@lru_cache()
def get_llm_settings() -> LLMSettings:
    """获取 LLM 配置单例"""
    return LLMSettings()


def get_llm_use_case(
    settings: LLMSettings = Depends(get_llm_settings),
) -> CreateLLMUseCase:
    """获取 LLM 创建用例"""
    return CreateLLMUseCase(settings=settings)

