"""基础设施层 - SQLAlchemy 数据库配置"""

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

# 数据库文件固定位于 backend/ 目录下，避免相对路径因工作目录不同导致多处生成 db 文件
# 目录层级：backend/src/infrastructure/database/session.py -> parents[3] = backend/
_DB_PATH = Path(__file__).resolve().parents[3] / "app.db"

# SQLite 数据库引擎 (同步 - 用于初始化)
SQLALCHEMY_DATABASE_URL = f"sqlite:///{_DB_PATH}"
SQLALCHEMY_ASYNC_DATABASE_URL = f"sqlite+aiosqlite:///{_DB_PATH}"

# 同步引擎 (用于初始化)
_SQLITE_CONNECT_ARGS = {"check_same_thread": False, "timeout": 30}

sync_engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args=_SQLITE_CONNECT_ARGS,
)

# 异步引擎 (用于异步操作)
# pool_size + max_overflow: 支持 sub-agent 并发场景（每 sub-agent 一个独立 session）
# WAL 模式通过 _init_wal() 在引擎创建后立即设置
async_engine = create_async_engine(
    SQLALCHEMY_ASYNC_DATABASE_URL,
    connect_args=_SQLITE_CONNECT_ARGS,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
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


def _init_wal() -> None:
    """启用 SQLite WAL 模式 + 性能优化 PRAGMA。

    WAL (Write-Ahead Logging) 允许读写并发，是 sub-agent 并行场景的核心优化。
    同时设置 synchronous=NORMAL（WAL 模式下安全）以提高写入性能。
    """
    from sqlalchemy import text

    with sync_engine.connect() as conn:
        # WAL 模式：持久化设置，影响所有后续连接
        result = conn.execute(text("PRAGMA journal_mode=WAL"))
        row = result.fetchone()
        if row and row[0].upper() != "WAL":
            # 某些配置下 WAL 可能被禁用（如只读文件系统），降级为 delete 模式
            import logging
            logging.getLogger(__name__).warning(
                "WAL mode not available (got: %s). Concurrent sub-agent performance may degrade.", row[0])

        # synchronous=NORMAL: WAL 模式下的安全降级，提升写入性能
        conn.execute(text("PRAGMA synchronous=NORMAL"))
        # cache_size: 增大页面缓存（单位：页，每页 4KB，-64000 ≈ 256MB）
        conn.execute(text("PRAGMA cache_size=-64000"))
        conn.commit()


def init_db():
    """初始化数据库(创建所有表 + 轻量列迁移 + WAL 优化)"""
    # 导入所有模型以注册
    from src.infrastructure.database.models.agent_model import (  # noqa: F401
        TaskModel,
        EventModel,
        AgentModel,
        SessionModel,
        SessionMessageModel,
        SkillModel,
    )

    # 启用 WAL 模式（必须在任何写入之前执行）
    _init_wal()

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
    _ensure_column(
        table="session_messages",
        column="thinking_content",
        column_def="TEXT NOT NULL DEFAULT ''",
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
