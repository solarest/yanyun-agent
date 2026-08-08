## Context

当前消息渲染的 `segments`（时间线片段）存在两条构建路径：

1. **前端流式路径**：`useChat.bindMessageStream()` 在收到 SSE 事件时通过 `appendSegmentContent()` 增量构建 `segments` 数组
2. **后端终态路径**：`TaskCompletionService._build_segments()` 从 LangGraph 原始 messages 完整解析重建

`session:message:saved` 事件到达时，前端 [useChat.ts:832-853](frontend/src/application/services/useChat.ts#L832-L853) 执行字段级合并：
- `content`: "流式与 DB 谁长用谁"
- `thinking_content`: "流式优先，DB fallback"
- `segments`: "流式优先，DB fallback"
- 其余字段: 全部使用 DB 版本

这种非结构化的合并策略在两个路径输出不一致时会产生错误结果。

另外，当 `segments` 已包含 `text` 类型片段时，`content` 字段中拼接的全轮次 AI 文本与 `segments` 中的 `text` 片段重复，[MessageBubble.tsx:403-564](frontend/src/presentation/components/chat/MessageBubble.tsx#L403-L564) 的新路径虽然已跳过 content 渲染，但旧路径仍会展示重复内容。

## Goals / Non-Goals

**Goals:**
- 后端 `_build_segments()` 成为 saved message segments 的唯一权威来源
- 前端删除 `session:message:saved` 事件中的所有"流式 vs DB"合并逻辑，完全信任 DB 消息
- segments 存在时，渲染路径永不回退到单独渲染 `content` 字段
- 前端流式期间保留 segments 增量构建，用于实时 UI 展示

**Non-Goals:**
- 不改变 SSE 事件格式或事件类型定义
- 不修改 LangGraph message 结构
- 不改变前端 streaming 期间的 segments 增量构建逻辑（仅改变 saved 后的行为）
- 不修改 tool_calls / tool_results 字段的保存逻辑
- 不引入消息格式迁移

## Decisions

### Decision 1: 后端 segments 为唯一权威来源

**选择**: `session:message:saved` 到达时，前端使用 saved message 的所有字段（包括 `segments`、`content`、`thinking_content`）完整替换流式构建的临时状态。

**备选方案**:
- *方案 A (当前)*: 字段级合并。被拒绝——各字段合并策略不一致，引入维护成本。
- *方案 B*: 前端 segments 为权威，保存到后端。被拒绝——后端 `_build_segments()` 可以从完整的 LangGraph messages 重建，前端流式构建可能因断联而不完整。

**理由**: 后端在 graph 执行完毕后拥有完整数据（所有 messages、tool_results、thinking_text），可以从容重建 segments，不受网络波动影响。

### Decision 2: segments 存在时完全抑制 content 渲染

**选择**: 在 MessageBubble 渲染路径中，当 `message.segments` 非空时，仅渲染 timeline，不渲染 `message.content` 作为独立块。

**当前状态**: 新路径（segments 存在时）已经跳过 content 渲染，但旧路径（无 segments）仍渲染 content。此决策确认并强制执行这一行为。

**理由**: `content` 字段保留其语义（作为搜索索引/文本摘要），但 UI 渲染中 timeline 是完整的视觉呈现。如果 segments 构建正确，所有 text 内容已包含在 text 类型片段中。

### Decision 3: 重构 `_build_segments()` 消息类型判断

**选择**: 将 `isinstance` + `type().__name__` + `hasattr` 三种混合判断统一为单个函数，按以下优先级判断：
1. `dict` 类型消息 → 检查 `role` 和 `tool_calls` 字段
2. LangChain Message 对象 → 检查类名，用 `AIMessage` / `HumanMessage` / `SystemMessage` / `ToolMessage` 作为白名单

**当前状态**: [task_completion_service.py:247-261](backend/src/application/services/task_completion_service.py#L247-L261) 中 `_is_ai()`、`_is_human_or_system()`、`_is_tool_msg()` 三个内部函数各自实现判断逻辑。

**理由**: 新增 LangChain 消息类型时（如 `AIMessageChunk` 聚合后的消息），`type().__name__` 可能等于 `AIMessage`（因为 `AIMessageChunk + AIMessageChunk = AIMessage`），但当前代码未覆盖此 case。统一判断降低遗漏风险。

### Decision 4: 保持 content 字段的 fallback 拼接语义

**选择**: `TaskCompletionService.finalize()` 中 `assistant_content` 的计算逻辑保持不变——clarify 输出优先，其次 final_result，最后 fallback 到 `extract_all_llm_content()`。

**理由**: `content` 仍在 DB 中保存，用于会话列表的 `last_message_preview` 和搜索功能。它不需要与 segments 精确一致，只需要提供合理的文本摘要。

## Risks / Trade-offs

- **[风险] segments 构建不完整**: 如果 `_build_segments()` 的消息类型推断漏掉某类消息，对应的 text 或 tool 片段会丢失 → **缓解**: Decision 3 统一判断逻辑 + 添加单元测试覆盖常见消息类型
- **[风险] 视觉闪烁**: saved message 的 `id` 与 placeholder 不同，React key 变化可能导致组件 remount → **缓解**: 当前代码已有 `mainMessageIdRef.current` 切换逻辑，且 saved message 内容应与流式内容一致
- **[权衡] CSS transition 断档**: 如果 saved message 的 segments 结构与流式构建的不同（如后端合并了连续 text 而前端未合并），替换瞬间可能看到布局变化 → **权衡**: 接受此风险，因为 `buildTimelineFromSegments()` 已合并同类型连续片段，两端输出应趋同

## Open Questions

1. `_build_segments()` 将所有 thinking 放在 segments 首位。多轮 ReAct 中 thinking 可能穿插在轮次间——是否需要改为按轮次插入 thinking？当前大部分模型仅在首轮产生 thinking，暂不处理此边缘 case。
2. 是否需要为历史消息（已保存但 segments 可能不正确的）提供迁移？当前不做迁移，仅保证新保存的消息正确。
