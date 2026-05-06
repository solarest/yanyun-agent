"""基础设施层 - SQLAlchemy 数据库配置"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

# SQLite 数据库引擎 (同步 - 用于初始化)
SQLALCHEMY_DATABASE_URL = "sqlite:///./app.db"
SQLALCHEMY_ASYNC_DATABASE_URL = "sqlite+aiosqlite:///./app.db"

# 同步引擎 (用于初始化)
sync_engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={
                            "check_same_thread": False})

# 异步引擎 (用于异步操作)
async_engine = create_async_engine(
    SQLALCHEMY_ASYNC_DATABASE_URL, connect_args={"check_same_thread": False}
)

# Session 工厂 (同步)
SessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=sync_engine)
AsyncSessionLocal = sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

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
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


def init_db():
    """初始化数据库(创建所有表 + 轻量列迁移)"""
    # 导入所有模型以注册
    from src.infrastructure.database.models.agent_model import (  # noqa: F401
        TaskModel,
        EventModel,
        AgentModel,
        SessionModel,
        SessionMessageModel,
        SkillModel,
    )

    Base.metadata.create_all(bind=sync_engine)

    # 轻量列迁移：兼容旧库（避免重建数据库）
    _ensure_column(
        table="sse_events",
        column="task_seq",
        column_def="INTEGER NOT NULL DEFAULT 0",
    )
    _ensure_column(
        table="skills",
        column="file_path",
        column_def="VARCHAR(500) DEFAULT ''",
    )


def _ensure_column(table: str, column: str, column_def: str) -> None:
    """若表已存在但缺少指定列，则 ALTER TABLE 追加（SQLite 兼容）。"""
    from sqlalchemy import text

    with sync_engine.connect() as conn:
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        existing_cols = {row[1] for row in rows}
        if not existing_cols:
            # 表不存在（理论上 create_all 已建好；这里防御性退出）
            return
        if column not in existing_cols:
            conn.execute(
                text(f"ALTER TABLE {table} ADD COLUMN {column} {column_def}"))
            conn.commit()
