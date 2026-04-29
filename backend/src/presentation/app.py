"""表现层 - FastAPI 应用工厂"""

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.infrastructure.database.session import init_db
from src.presentation.routes.llm_config import router as llm_router
from src.presentation.routes.ping import router as ping_router
from src.presentation.routes.sse_stream import router as sse_router
from src.presentation.routes.tasks import router as tasks_router
from src.presentation.routes.agents import router as agents_router
from src.presentation.routes.sessions import router as sessions_router

# 加载 .env 环境变量（供 os.getenv 使用）
load_dotenv()


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用"""
    app = FastAPI(
        title="DDD Python Backend", description="DDD 架构的 Python 后端脚手架", version="0.1.0"
    )

    # 配置 CORS(允许前端访问)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],  # 前端地址
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册路由
    app.include_router(ping_router)
    app.include_router(tasks_router)
    app.include_router(sse_router)
    app.include_router(llm_router)
    app.include_router(agents_router)
    app.include_router(sessions_router)

    # 初始化数据库
    init_db()

    # 全局共享的 StreamEventService（SSE 事件需要单例以共享订阅）
    from src.infrastructure.database.session import async_engine
    from sqlalchemy.ext.asyncio import AsyncSession as SAAsyncSession
    from src.infrastructure.repositories.sqlite_event_repo import SQLiteEventRepository
    from src.application.use_cases.stream_event import StreamEventService

    _event_db = SAAsyncSession(async_engine)
    _event_repo = SQLiteEventRepository(_event_db)
    app.state.event_service = StreamEventService(_event_repo)

    # 全局状态
    app.state.running_tasks = {}  # task_id -> asyncio.Task

    @app.get("/health")
    async def health_check():
        """健康检查接口"""
        return {"status": "ok", "service": "ddd-python-backend"}

    return app


# 应用实例(用于 uvicorn 启动)
app = create_app()
