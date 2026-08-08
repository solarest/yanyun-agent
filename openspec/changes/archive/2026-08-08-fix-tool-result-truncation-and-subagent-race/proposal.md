## Why

两个 P1 级别问题威胁系统稳定性和数据完整性：(1) 工具执行结果无截断保护，`cat /var/log/syslog` 等操作可将数十 MB 数据全量写入 SSE 事件流、SQLite JSON 列和浏览器内存；(2) 页面刷新恢复 SSE 连接时，sub-agent 消息回放逻辑存在竞态——`subAgentMessagesRef` 在 disconnect 时被清空但消息列表中已有持久化内容，导致回放的 `sub_agent:started` 创建空 placeholder 覆盖已保存数据。

## What Changes

- 工具输出截断：在 SSE 事件发射和 all_tool_results 收集两个关键路径上，对超过阈值（默认 50KB）的工具输出进行截断，附加 `[truncated: N chars → 50KB]` 标记
- Sub-agent 回放防护：`connectSubAgentStream` 在创建 placeholder 前检查消息列表中是否已存在非 streaming 状态的同 ID 消息，避免覆盖持久化数据
- 截断常量化：定义 `MAX_TOOL_OUTPUT_SIZE` 常量为 50KB，集中管理截断阈值
- **BREAKING**：工具结果超过 50KB 时，SSE 推送和 DB 存储均使用截断版本（日志写入完整版不受影响）

## Capabilities

### New Capabilities
- `tool-output-truncation`: 工具执行结果在 SSE 推送和 DB 持久化路径上强制截断，防止大数据膨胀
- `subagent-replay-guard`: sub-agent 消息回放时检查消息列表已有数据，避免用空 placeholder 覆盖已持久化内容

### Modified Capabilities
<!-- No existing spec changes needed -->

## Impact

- **后端**: `infrastructure/agent/nodes/tool_execute_node.py` — `_execute_single_tool()` 中 SSE 事件发射和 result_dict 输出截断
- **后端**: `application/services/task_completion_service.py` — `finalize()` 中 `all_tool_results` 收集时截断
- **前端**: `application/services/useChat.ts` — `connectSubAgentStream()` 增加消息列表检查
- **常量**: `domain/services/tool_output_limits.py` — 新增截断常量定义
