## Context

当前架构中 session 执行过程态有三个存储目标：

```
过程态 (当前)                          最终态 (当前)
─────────────────                     ────────────────
sse_events 表 ← 每事件一行             session_messages ← finalize 时写
AgentState   ← 进程内存 (丢失)         tasks           ← RUNNING→COMPLETED
用户消息     ← 同步写 session_messages  sessions        ← 元数据

问题:
• sse_events 表随对话膨胀，SQLite 写入竞争
• AgentState 在内存，进程重启丢 checkpoint，无法 resume
• 用户消息提前入库，finalize 失败时留孤儿行
```

改造后：

```
过程态 (新)                            最终态 (新)
─────────────────                     ────────────────
本地文件                               DB (原子事务)
  events.jsonl                         session_messages (user+assistant 同时写)
  checkpoints/turn_N.json              tasks (COMPLETED)
  user_msg.json                        sessions (元数据)
  meta.json                            
sub-agent: 独立文件目录                 sse_events 表 — 删除 ✗

优势:
• SQLite 只存最终结果，写入量大幅减少
• checkpoint 落盘，进程重启可 resume
• 用户消息 + 助手消息原子写入，无孤儿行
• 文件可压缩/归档，不占 DB 空间
```

## Goals / Non-Goals

**Goals:**
- 过程态 SSE 事件全量写入本地 `events.jsonl` 文件
- 每轮 ReAct 后保存 AgentState checkpoint 到本地文件
- 删除 `sse_events` 表
- 用户消息 finalize 时与 assistant 消息一起原子写入 DB
- SSE 重连支持文件回放 + checkpoint 恢复
- Sub-agent 过程态存储为独立文件目录
- Tool output 截断区分路径：SSE 推送/文件存储/DB 持久化

**Non-Goals:**
- 不修改 LangGraph 的 ToolMessage 内容（LLM 推理仍需完整输出）
- 不修改 SSE 事件协议格式（前端兼容）
- 不修改 session/task 的核心业务逻辑
- 不处理历史 `sse_events` 数据迁移（直接丢弃）
- 不引入文件压缩/加密（后续迭代）

## Decisions

### Decision 1: 文件存储结构

**选择**: 按 session → task 两级目录组织：

```
storage/sessions/<session_id>/<task_id>/
├── events.jsonl              ← SSE 事件流，每行一个 JSON 事件
├── checkpoints/
│   └── turn_N.json           ← 第 N 轮 ReAct 后的 AgentState 快照
├── user_msg.json             ← 用户消息内容（finalize 时读取）
├── meta.json                 ← task 元信息（创建时间、agent_id 等）
└── sub_agents/
    └── <sub_task_id>/        ← sub-agent 独立目录
        ├── events.jsonl
        └── checkpoints/
```

**理由**: 按 session→task 分区，天然隔离；`events.jsonl` 追加写入友好；checkpoint 按 turn 编号便于恢复。

**备选**: 单文件（所有数据混在一起）— 读写冲突，放弃。

### Decision 2: Checkpointer 持久化 — LLM 调用前 + interrupt 后

**选择**: 新增 `save_checkpoint_node`，置于 `context_compact` 与 `llm_call` 之间，在每次 LLM 调用前将 `MemorySaver` 内部状态序列化为 JSON 文件 `checkpointer.json`。人机回路中断后由 `AgentLoopRunner` 额外保存一次（此时 `writes` 已填充）。

```
Graph 结构:
  context_compact → ★ save_checkpoint_node → llm_call → [tool_execute | END]
                                                              │
                                               interrupt() ──┘
                                                    │
                                         GraphInterrupt
                                                    │
                                    AgentLoopRunner 补存 checkpointer.json
                                    (此时 writes 已生成)
```

**理由**: 

- **LLM 调用前是最佳恢复点** — LLM 调用是唯一有外部副作用（token 消耗、API 费用）且可能失败的步骤。在调用前保存，崩溃后恢复不会重复调用 LLM。
- **interrupt 后需要补存** — `save_checkpoint_node` 在 LLM 调用前执行，interrupt 发生在之后的 `tool_execute_node` 中，此时 `MemorySaver.writes` 已有待恢复数据。需要额外保存。
- **JSON 而非 pickle** — `MemorySaver` 内部使用 `msgpack` 序列化，binary 数据用 base64 编码存储为 JSON，可读可调试。

**checkpointer.json 内容**:

```json
{
  "thread_id": "task-001",
  "storage": {
    "": {
      "checkpoint_id": {
        "checkpoint": {"tag": "msgpack", "data": "<base64>"},
        "metadata":   {"tag": "msgpack", "data": "<base64>"},
        "parent": "parent_id"
      }
    }
  },
  "writes": {
    "task_id": [
      ["channel", {"tag": "msgpack", "data": "<base64>"}]
    ]
  }
}
```

`writes` 是 `Command(resume=)` 正确恢复的前提 — 它记录了 `interrupt()` 时节点"本该写入"的 state 更新，没有它 LangGraph 不知道从哪个状态继续。

### Decision 2b: AgentState checkpoint 保留为辅助

AgentState 快照 `checkpoints/turn_N.json` **保留**，用于：
- 调试检查 agent 状态
- `HistoryLoader` 若需离线重建对话上下文
- 不参与 resume 流程（resume 完全依赖 `checkpointer.json`）

### Decision 3: SSE 重连策略

**选择**: 根据 task 状态分两路：

```
GET /api/tasks/{task_id}/stream
│
├─► task.status = COMPLETED / FAILED
│     └─► 读 events.jsonl → 全量回放所有历史事件 → 关闭连接
│
├─► task.status = RUNNING
│     ├─► 读 events.jsonl → 回放已有事件（支持 Last-Event-ID 增量）
│     ├─► checkpointer.json 存在 → 加载，重建 graph + config
│     │     └─► graph.ainvoke(state, config) → 继续执行 → 推流
│     ├─► checkpointer.json 不存在 → 仅回放，不恢复执行
│     └─► 订阅新事件 → 推送到 SSE 连接
│
└─► task 不存在 / 文件缺失 → 404
```

**理由**: 已完成任务只需回放不需恢复。进行中任务通过 `checkpointer.json` 恢复 `MemorySaver` 状态后重建 graph 继续执行。无 checkpointer 文件时仅回放已有事件（无法恢复执行）。

### Decision 3b: 审批恢复（/approvals）

**选择**: 进程重启后，`/approvals` 端点从 `checkpointer.json` 加载状态恢复执行，替代原 `GraphResumeManager`。

```
进程内（GraphResumeManager 保留）:
  GraphInterrupt → resume_mgr.register(graph, config)
  → /approvals → resume_mgr.resume(task_id, decision)
  → graph.ainvoke(Command(resume=decision), config)

进程重启后（checkpointer.json 恢复）:
  /approvals 收到 decision
  → 加载 checkpointer.json → 恢复 MemorySaver
  → 重建 graph（AgentWorkflowBuilder.build()）
  → 重建 config（llm, event_emitter, tool_registry 等从 DI 重新注入）
  → graph.ainvoke(Command(resume=decision), config)
  → 继续执行 → finalize
```

**config 重建**: `checkpointer.json` 旁存一个 `resume_meta.json`，包含 `agent_id`, `session_id`, `model`, `workspace` 等必要参数，恢复时从这些参数重新构建 `config["configurable"]` 中的依赖对象。

### Decision 4: 用户消息延迟入库

**选择**: HTTP request 阶段不再写 `session_messages` 用户行，改为写 `user_msg.json` 文件。`finalize()` 时同时写入 user + assistant 两条 `session_messages` 行，在同一个 DB 事务内。

**理由**: 如果 agent 执行失败/取消，DB 里不会留下孤立的用户消息。用户消息和助手消息形成原子对话对。

**错误处理**: 如果文件写入失败 → 返回 500 给 HTTP 请求（同步阶段可感知）。如果 finalize 时文件读取失败 → task 标记 FAILED，原始文件保留供排查。

### Decision 5: Sub-agent 文件归属

**选择**: Sub-agent 创建独立文件目录 `sub_agents/<sub_task_id>/`，位于父 task 目录下。SSE 事件写入自己的 `events.jsonl`，通过 `ProxyEventEmitter` 转发到父 task 的 SSE 连接。

**理由**: 
- 隔离性：sub-agent 执行故障不影响父 task 文件完整性
- 可追溯：sub-agent 有独立的事件流和 checkpoint
- 清理：父 task 删除时子目录一并清理

### Decision 6: Tool output 截断三路径

**选择**: 同一份 tool output，三条路径不同处理：

```
tool 执行返回 (100KB)
│
├─► LangGraph ToolMessage  →  完整      (LLM 推理需要)
├─► SSE live push          →  截断 50KB  (省带宽，前端展示)
├─► events.jsonl 写入      →  完整      (回放/调试数据源)
└─► DB tool_results        →  截断 +     (DB 精简，文件可查完整)
                                file_ref 指针
```

**file_ref 格式**: `storage/sessions/<s_id>/<t_id>/tool_results/<tool_call_id>.txt`

每条 tool result 写入独立文件，`session_messages.tool_results` JSON 列中存储：
```json
{
  "tool_call_id": "call_xxx",
  "name": "file_read",
  "result": "[truncated: 100KB → 50KB] <前50KB内容>...",
  "full_result_ref": "tool_results/call_xxx.txt"
}
```

### Decision 7: events.jsonl 格式

**选择**: JSONL 格式（每行一个完整 JSON 事件）。

```jsonl
{"seq":1,"type":"task:started","data":{...},"timestamp":"2026-08-01T10:00:00Z"}
{"seq":2,"type":"llm:chunk","data":{"content":"Hello"},"timestamp":"2026-08-01T10:00:01Z"}
```

**理由**: 追加写入 O(1)，无需解析整个文件即可增量读取，支持 Last-Event-ID 增量回放（按 seq 号 seek）。

### Decision 8: sse_events 表处理

**选择**: 直接删除 `sse_events` 表和相关 ORM 模型、repository。历史数据不迁移。

**理由**: 已确认不需要（用户决策 A）。历史 `sse_events` 数据价值低——已完成任务的回放可从文件做，未完成的任务回放也不需要 DB 里的旧事件。

## Risks / Trade-offs

- **[风险] 文件 I/O 性能**: 每个事件都写 `events.jsonl` → **缓解**: JSONL 追加写是顺序 I/O，现代 SSD 上性能优于 SQLite INSERT；checkpoint 每轮一次而非每事件，频率低
- **[风险] 磁盘空间**: 文件不清理，长时间运行后磁盘增长 → **缓解**: 后续可加归档/压缩策略（non-goal 本次不做）；当前 session 量级下可控
- **[风险] 并发写入**: 同一 task 的事件写是单线程的（graph 执行串行）；不同 task 的文件目录隔离，无竞争
- **[风险] Checkpoint 序列化**: AgentState 中可能含不可序列化对象（LangGraph messages 对象等）→ **缓解**: 需要实现专用序列化/反序列化逻辑，将 LangChain 消息转为 dict
- **[权衡] 文件管理复杂度**: 相比 SQLite 单文件，引入目录结构、文件清理、权限管理 → **权衡**: 换来清晰的边界和简洁的 DB schema。操作层面，session 删除时 `rm -rf` 即可

## Open Questions

1. Checkpoint 文件是否需要压缩？当前不做（non-goal），量大再考虑
2. 文件路径中的 session_id/task_id 是否需要哈希/编码防止路径遍历？当前 project 内部使用，信任输入
3. Sub-agent checkpoint 是否需要支持 resume？当前 sub-agent 生命周期短（单次 tool 调用），暂不实现
