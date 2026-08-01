## Why

当前 session 执行过程态（SSE 事件流、AgentState checkpoint、用户消息）混杂在 DB 和内存中，带来三个核心问题：

1. **DB 膨胀**：`sse_events` 表存储每一条 LLM chunk、tool call/result 事件，大输出场景下单 task 可产生数万行，SQLite 写入成为瓶颈且数据价值密度低
2. **无法 resume**：`AgentState` 和 `MemorySaver` checkpoint 仅存于进程内存，进程重启/崩溃后中断的 agent 执行不可恢复，用户只能重新发起对话
3. **存储语义混乱**：过程态和最终态无清晰边界——用户消息同步写 DB、assistant 消息延迟到 finalize 才写、SSE 事件每条都写——运维和理解成本高

## What Changes

- **sse_events 表删除**：过程事件流改为本地文件 `events.jsonl` 存储，重连回放从文件读取
- **Checkpoint 机制**：每轮 ReAct（llm_call → tool_execute）完成后，将 AgentState 快照写入本地文件 `checkpoints/turn_N.json`，支持进程重启后从最近 checkpoint 恢复执行
- **用户消息延迟入库**：用户消息不再同步写 `session_messages`，改为暂存本地文件，finalize 时与 assistant 消息原子写入
- **Sub-agent 独立文件**：sub-agent 过程态文件保存在父 task 目录下的 `sub_agents/<sub_task_id>/`
- **Tool output 截断策略调整**：SSE live push 截断（50KB），`events.jsonl` 完整保存，DB `tool_results` 截断 + `file_ref` 指针
- **SSE 重连改造**：已完成 task → 读文件全量回放；进行中 task → 回放文件事件 + 恢复 checkpoint → 继续驱动 loop

## Capabilities

### New Capabilities
- `session-file-storage`: 会话过程态本地文件存储，替代 `sse_events` 表和消息提前写库
- `checkpoint-resume`: ReAct 级 checkpoint 与 graph 中断恢复

### Modified Capabilities
- `tool-output-truncation`: 截断策略调整——区分 SSE 推送/文件存储/DB 持久化三个路径

## Impact

- **后端**: `StreamEventService` → 改为文件写入；`TaskCompletionService.finalize()` → 原子写入 user+assistant 消息；`AgentLoopLifecycle` → checkpoint 调度
- **后端**: 新增 `SessionFileStorage` 服务（目录管理、事件追加、checkpoint 读写）
- **后端**: `AgentLoopRunner` / `AgentLoopContext` — 支持从 checkpoint 恢复
- **前端**: SSE 重连逻辑调整——区分"已持久化"和"进行中"两种回放
- **DB**: 删除 `sse_events` 表，`sessions`/`session_messages`/`tasks` 保留但写入时机调整
- **BREAKING**: `sse_events` 表删除，历史数据不迁移；SSE 重连数据源从 DB 改为文件
