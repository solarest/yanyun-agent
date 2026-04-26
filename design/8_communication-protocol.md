# 3. 通信协议设计

> 对应 `0_outline.md` 第 3 章

## SSE 实现

后端通过 Server-Sent Events 向客户端推送流式事件。

### 核心机制

| 机制 | 说明 |
|------|------|
| 连接保活 | 定期发送 keep-alive |
| 断线重连 | 客户端自动重连 |
| 消息顺序 | 序列号保证顺序 |

## 事件 Schema

### 事件定义

| 事件类型 | 说明 |
|----------|------|
| `llm:chunk` | LLM 流式输出 |
| `llm:done` | LLM 输出完成 |
| `tool:start` | 工具调用开始 |
| `tool:result` | 工具调用结果 |
| `task:status` | 任务状态变更 |
| `agent:thought` | Agent 思考过程 |

### 消息结构

```python
class SSEEventDTO:
    id: str          # 事件 ID（序列号）
    task_id: str     # 关联任务
    type: str        # 事件类型
    payload: dict    # 事件载荷
    timestamp: str   # ISO 8601 时间戳
```

## 实现位置

```
application/use_cases/stream_event.py  — 事件服务
presentation/routes/sse_stream.py      — SSE 路由
infrastructure/api/eventStream.ts      — 前端事件流
```

## 流式背压

客户端处理慢时，服务端控制推送速率。

## 重连状态恢复

- 事件 ID 序号追踪
- 未确认消息重发
- 幂等处理
