"""表现层 - SSE 流式路由"""

import asyncio
import json
import logging
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from src.application.dtos.event_dto import normalize_event_type, to_sse_event_name

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("/{task_id}/stream")
async def stream_events(task_id: str, request: Request):
    """SSE 事件流端点

    客户端连接后：
    1. 先订阅实时队列（防止回放期间丢失新事件）
    2. 回放已有事件（处理晚于任务启动的连接）
    3. 对于 RUNNING 任务，尝试从 checkpointer.json 恢复执行
    4. 从队列读取新事件（跳过已回放的）
    """
    event_service = request.app.state.event_service

    def format_sse(event_json: str) -> str:
        """将 JSON 格式的事件转换为 SSE 协议字符串"""
        event = json.loads(event_json)
        event["event_type"] = normalize_event_type(str(event.get("event_type", "message")))
        normalized_json = json.dumps(event, ensure_ascii=False)
        return (
            f"id: {event['id']}\n"
            f"event: {to_sse_event_name(event['event_type'])}\n"
            f"data: {normalized_json}\n\n"
        )

    async def event_generator():
        queue = await event_service.subscribe(task_id)
        max_replayed_seq = 0

        try:
            # === 1. 回放已有事件 ===
            last_event_id = request.headers.get("last-event-id")
            if last_event_id:
                existing_events = await event_service.get_events_after(
                    task_id, last_event_id
                )
            else:
                existing_events = await event_service.get_all_events(task_id)

            for event_json in existing_events:
                event_data = json.loads(event_json)
                seq = int(event_data.get("id", "0"))
                if seq > max_replayed_seq:
                    max_replayed_seq = seq
                yield format_sse(event_json)

            # === 2. 尝试恢复 RUNNING 任务的 graph 执行 ===
            await _try_resume_task(task_id, event_service)

            # === 3. 实时事件流（跳过已回放的） ===
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event_json = await asyncio.wait_for(queue.get(), timeout=15.0)
                    event_data = json.loads(event_json)
                    seq = int(event_data.get("id", "0"))
                    if seq > max_replayed_seq:
                        yield format_sse(event_json)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            await event_service.unsubscribe(task_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _try_resume_task(task_id: str, event_service) -> None:
    """Try to resume a RUNNING task from checkpointer.json."""
    from src.infrastructure.database.session import AsyncSessionLocal
    from src.infrastructure.repositories.sqlite_task_repo import SQLiteTaskRepository
    from src.application.services.session_file_storage import SessionFileStorage
    from src.infrastructure.agent.file_backed_saver import FileBackedSaver
    from src.infrastructure.agent.workflow_builder import AgentWorkflowBuilder

    try:
        async with AsyncSessionLocal() as db:
            task_repo = SQLiteTaskRepository(db)
            task = await task_repo.get_by_id(task_id)
            if task is None or task.status != "running":
                return

            session_id = task.session_id
            file_storage = SessionFileStorage()
            task_dir = file_storage.base_path / session_id / task_id
            ckpt_file = task_dir / "checkpointer.json"
            meta_file = task_dir / "resume_meta.json"

            if not ckpt_file.exists():
                return

            # Load checkpointer state and rebuild graph
            saver = FileBackedSaver(file_path=str(ckpt_file))
            graph = AgentWorkflowBuilder.build_with_checkpointer(saver)

            # Build config with event emitter for live streaming
            config = {
                "configurable": {
                    "thread_id": task_id,
                    "checkpoint_ns": "",
                    "event_emitter": event_service,
                    "llm_model": task.model if hasattr(task, 'model') else None,
                    "session_id": session_id,
                }
            }

            # Resume in background with task finalization
            async def _run():
                from datetime import datetime
                try:
                    result = await graph.ainvoke(None, config)
                    logger.info("SSE resume: task %s completed", task_id)
                    # Update task status
                    task.status = "completed"
                    task.completed_at = datetime.now()
                    task.result = result.get("final_result") if isinstance(result, dict) else None
                    await task_repo.update(task)
                except Exception:
                    logger.exception("SSE resume: task %s failed", task_id)
                    try:
                        task.status = "failed"
                        task.completed_at = datetime.now()
                        await task_repo.update(task)
                    except Exception:
                        pass

            asyncio.create_task(_run())
            logger.info("SSE resume: started background execution for task %s", task_id)

    except Exception:
        logger.exception("SSE resume: failed to start for task %s", task_id)
