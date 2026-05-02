"""表现层 - FastAPI 应用工厂"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.infrastructure.database.session import init_db
from src.presentation.routes.llm_config import router as llm_router
from src.presentation.routes.sse_stream import router as sse_router
from src.presentation.routes.tasks import router as tasks_router
from src.presentation.routes.agents import router as agents_router
from src.presentation.routes.sessions import router as sessions_router

# 加载 .env 环境变量（供 os.getenv 使用）
load_dotenv()


def _setup_logging() -> None:
    """初始化全局日志配置

    - 根 logger 设置为 INFO，输出到 stdout（被 uvicorn/bootstrap 重定向到 backend.log）
    - `llm.call` logger 额外写入独立文件 logs/llm-call.log
    - `tool.call` logger 额外写入独立文件 logs/tool-call.log
    """
    root_logger = logging.getLogger()
    if not any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers):
        root_logger.setLevel(logging.INFO)
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        root_logger.addHandler(stream_handler)

    log_dir = Path(os.getenv("LLM_LOG_DIR", Path(__file__).resolve().parents[3] / "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)

    _attach_file_handler(logging.getLogger("llm.call"), log_dir / "llm-call.log", tag="_llm_call_tag")
    _attach_file_handler(logging.getLogger("tool.call"), log_dir / "tool-call.log", tag="_tool_call_tag")


def _attach_file_handler(target_logger: logging.Logger, file_path: Path, tag: str) -> None:
    """为指定 logger 挂载独立的 FileHandler（通过 tag 属性防止 reload 时重复注册）"""
    target_logger.setLevel(logging.INFO)
    if any(getattr(h, tag, False) for h in target_logger.handlers):
        return
    file_handler = logging.FileHandler(file_path, encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    )
    setattr(file_handler, tag, True)
    target_logger.addHandler(file_handler)


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用"""
    # 初始化日志（务必在创建路由/业务对象之前）
    _setup_logging()

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
    app.include_router(tasks_router)
    app.include_router(sse_router)
    app.include_router(llm_router)
    app.include_router(agents_router)
    app.include_router(sessions_router)

    # 初始化数据库
    init_db()

    # 全局共享的 StreamEventService（SSE 事件需要单例以共享订阅）
    from src.application.use_cases.stream_event import StreamEventService
    from src.presentation.dependencies import create_event_repo_factory

    app.state.event_service = StreamEventService(create_event_repo_factory())

    # 全局状态
    app.state.running_tasks = {}  # task_id -> asyncio.Task
    app.state.approval_requests = {}  # task_id -> PendingApprovalContext

    @app.get("/health")
    async def health_check():
        """健康检查接口"""
        return {"status": "ok", "service": "ddd-python-backend"}

    return app


# 应用实例(用于 uvicorn 启动)
app = create_app()
