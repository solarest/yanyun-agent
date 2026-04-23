"""基础设施层 - SQLAlchemy 数据库配置"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

# SQLite 数据库引擎 (同步 - 用于初始化)
SQLALCHEMY_DATABASE_URL = "sqlite:///./app.db"
SQLALCHEMY_ASYNC_DATABASE_URL = "sqlite+aiosqlite:///./app.db"

# 同步引擎 (用于初始化)
sync_engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})

# 异步引擎 (用于异步操作)
async_engine = create_async_engine(
    SQLALCHEMY_ASYNC_DATABASE_URL, connect_args={"check_same_thread": False}
)

# Session 工厂 (同步)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)

# Base 类用于声明 ORM 模型
Base = declarative_base()


def get_db():
    """获取数据库 Session 的依赖注入函数 (同步)

    用法:
        @router.get("/example")
        def example(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_async_db():
    """获取异步数据库 Session 的依赖注入函数

    用法:
        @router.get("/example")
        async def example(db: AsyncSession = Depends(get_async_db)):
            ...
    """
    async with AsyncSession(async_engine) as session:
        try:
            yield session
        finally:
            await session.close()


def init_db():
    """初始化数据库(创建所有表)"""
    # 导入所有模型以注册
    from src.infrastructure.database.models.agent_model import TaskModel, EventModel, AgentModel  # noqa: F401

    Base.metadata.create_all(bind=sync_engine)
