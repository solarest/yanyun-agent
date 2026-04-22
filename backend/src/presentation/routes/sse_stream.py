"""表现层 - SSE 流式路由"""

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.get("/{task_id}/stream")
async def stream_events(task_id: str, request: Request):
    """SSE 事件流端点

    客户端连接后：
    1. 如果有 Last-Event-ID，补发缺失事件
    2. 订阅实时事件流
    3. 客户端断开时自动取消订阅
    """
    event_service = request.app.state.event_service

    def format_sse(event_json: str) -> str:
        """将 JSON 格式的事件转换为 SSE 协议字符串"""
        import json

        event = json.loads(event_json)
        return (
            f"id: {event['id']}\n"
            f"event: {event['event_type'].replace(':', '-')}\n"
            f"data: {event_json}\n\n"
        )

    async def event_generator():
        # === 1. 补发缺失事件 ===
        last_event_id = request.headers.get("last-event-id")
        if last_event_id:
            missed_events = await event_service.get_events_after(task_id, last_event_id)
            for event_json in missed_events:
                yield format_sse(event_json)

        # === 2. 实时事件流 ===
        queue = await event_service.subscribe(task_id)
        try:
            while True:
                # 检查客户端是否断开连接
                if await request.is_disconnected():
                    break

                try:
                    # 15 秒超时 → 发送心跳
                    event_json = await asyncio.wait_for(queue.get(), timeout=15.0)
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
