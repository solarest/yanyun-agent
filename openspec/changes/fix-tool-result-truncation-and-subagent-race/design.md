## Context

两个独立但同属 P1 优先级的问题：

1. **工具输出无截断**：`tool_execute_node.py` 将 `result.output`（可能数十 MB）完整写入 SSE 事件 JSON → `sse_events` 表 → `session_messages.tool_results` JSON 列 → 前端 EventSource 内存。日志预览截断 200 字符但实际数据全量通行。

2. **Sub-agent 回放竞态**：页面刷新时 `useChat.restoreActiveStream()` 会断开旧连接（`disconnectAllStreams()` → 清空 `subAgentMessagesRef`），然后重连 SSE。后端回放所有历史事件（包括 `sub_agent:started`），`connectSubAgentStream()` 仅检查 `subAgentMessagesRef`（此时为空）而忽略消息列表中已存在的持久化消息，导致 `onUpsertMessage` 用空 placeholder 覆盖已有内容。

## Goals / Non-Goals

**Goals:**
- 50KB 以上的工具输出在 SSE 推送和 DB 存储前截断
- Sub-agent 回放时检测消息列表中的已有数据，跳过已持久化的 sub-agent
- 截断常量化，方便后续调整

**Non-Goals:**
- 不改变工具执行的完整输出（工具内部仍可访问完整数据）
- 不改变日志记录（日志仍记录完整长度的预览）
- 不修改 sub-agent 消息在消息列表中的存储结构
- 不修改 `subAgentMessagesRef` 的用途（仍用于流式期间的防重）

## Decisions

### Decision 1: 截断位置 — SSE 发射点和 DB 收集点

**选择**: 在数据进入 SSE 和 DB 持久化路径时截断，而非在工具执行时截断。

**理由**: `result.output` 在工具链内部仍需完整数据（如一个工具的输出作为另一个工具的输入）。截断仅应影响对外暴露的路径。

**两个截断点**:
1. `_execute_single_tool()` — 构建 `result_dict["output"]` 前截断（控制 SSE 事件 + AgentState.tool_results）
2. `TaskCompletionService.finalize()` — 构建 `all_tool_results` 前截断（控制 SessionMessage.tool_results + SSE 回放事件）

### Decision 2: 截断阈值 — 50KB

**选择**: `MAX_TOOL_OUTPUT_SIZE = 51200`（50KB）。

**备选**: 20KB（太小，可能截断有用数据）、100KB（太大，仍可能撑爆 SSE）。50KB 是中间值——足够容纳典型工具输出（文件读取、shell 命令），对于 log 文件等极端场景有保护。

**截断标记**: 附加 `[truncated: 原始N字符 → 50KB]` 后缀，让前端/日志知道发生了截断。

### Decision 3: Sub-agent 消息存在性检查 — 消息列表

**选择**: `connectSubAgentStream()` 在创建 placeholder 前，遍历 `messages` 数组检查是否已存在 `id === subTaskId` 且 `status !== 'streaming'` 的消息。

**理由**: `subAgentMessagesRef` 是内存态（连接生命周期），消息列表是持久化态。回放场景下，持久化的 sub-agent 消息从 API 恢复到了消息列表里，但 ref 已被清空。

**检查逻辑**:
```
if (消息列表中存在 id === subTaskId 且 status !== 'streaming') → 跳过（已持久化）
if (subAgentMessagesRef.has(subTaskId)) → 跳过（已有流式 placeholder）
else → 创建 placeholder
```

### Decision 4: 截断常量化

**选择**: 定义 `domain/services/tool_output_limits.py`，包含 `MAX_TOOL_OUTPUT_SIZE` 和 `truncate_tool_output()` 工具函数。

**理由**: 避免魔法数字散落在多处，便于将来从配置读取。

## Risks / Trade-offs

- **[风险] 截断 Data Loss**: Agent 依赖工具完整输出做后续推理 → **缓解**: 工具内部 `result.output` 保持完整，仅持久化层截断。Agent 在同一 turn 内的工具链可访问完整输出。
- **[风险] 多轮上下文截断**: 如果截断后的输出进入 LangGraph messages，后续 turn 的 LLM 将无法看到完整输出 → **缓解**: LangGraph 的 ToolMessage 由 `result_dict` 构建，若截断发生在 `result_dict` 之前，LLM 上下文也会受影响。因此在 `result_dict` 构建时不截断，仅在 SSE 事件发射和 `all_tool_results` 收集时截断。
- **[权衡] Sub-agent 检查性能**: 每次 `sub_agent:started` 事件都需 O(n) 扫描消息列表 → **权衡**: 消息列表通常在百条以内，线性扫描可接受。

## Open Questions

1. 截断阈值是否需要可配置？当前硬编码 50KB，如果业务需要调整，可后续改为环境变量 `MAX_TOOL_OUTPUT_SIZE`。
2. Sub-agent 的消息列表检查是否需要防抖？回放模式下大量事件快速到达，短时间内多次 `sub_agent:started` 事件可能触发多次扫描。当前不做防抖，因为每次扫描成本低且结果一致。
