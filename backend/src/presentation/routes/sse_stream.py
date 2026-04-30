"""表现层 - SSE 流式路由"""

import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from src.application.dtos.event_dto import normalize_event_type, to_sse_event_name

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("/{task_id}/stream")
async def stream_events(task_id: str, request: Request):
    """SSE 事件流端点

    客户端连接后：
    1. 先订阅实时队列（防止回放期间丢失新事件）
    2. 回放已有事件（处理晚于任务启动的连接）
    3. 从队列读取新事件（跳过已回放的）
    4. 客户端断开时自动取消订阅
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
        # === 1. 先订阅队列，确保回放期间的新事件不丢失 ===
        queue = await event_service.subscribe(task_id)
        max_replayed_seq = 0

        try:
            # === 2. 回放已有事件 ===
            last_event_id = request.headers.get("last-event-id")
            if last_event_id:
                # 断线重连：只回放缺失的
                existing_events = await event_service.get_events_after(
                    task_id, last_event_id
                )
            else:
                # 首次连接：回放全部已有事件
                existing_events = await event_service.get_all_events(task_id)

            for event_json in existing_events:
                event_data = json.loads(event_json)
                seq = int(event_data.get("id", "0"))
                if seq > max_replayed_seq:
                    max_replayed_seq = seq
                yield format_sse(event_json)

            # === 3. 实时事件流（跳过已回放的） ===
            while True:
                if await request.is_disconnected():
                    break

                try:
                    event_json = await asyncio.wait_for(queue.get(), timeout=15.0)
                    event_data = json.loads(event_json)
                    seq = int(event_data.get("id", "0"))
                    # 跳过已回放的事件
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
            "X-Accel-Buffering": "no",  # 禁止 Nginx 缓冲
        },
    )
