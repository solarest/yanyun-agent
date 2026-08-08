## Why

消息渲染核心数据 `segments`（时间线片段）当前在两处独立构建——前端 SSE 流式增量拼接和后端 `TaskCompletionService._build_segments()` 终态重建——合并时使用"谁长用谁"等非结构化启发式规则，导致历史消息时间线渲染与流式展示不一致。同时 `content` 字段在 segments 存在时语义重叠，造成内容重复渲染。

## What Changes

- **BREAKING**: 后端 `_build_segments()` 改为统一的 segments 构建入口，作为 saved message 的唯一权威来源
- 前端删除 `session:message:saved` 事件处理器中基于"内容更长"和"流式 segments 优先"的合并逻辑，改为完全信任 DB 保存的 segments
- 前端渲染路径中，当 segments 存在时不再回退渲染 `content`（segments 已包含 text 片段）
- 前端流式期间保留 segments 增量构建用于实时展示，但仅作为短暂的临时状态，saved message 到达后替换
- 重构 `_build_segments()` 中的消息类型判断逻辑，统一为注册表模式，消除 `isinstance` + `type().__name__` + `hasattr` 的三种混合判断

## Capabilities

### New Capabilities
- `segments-single-source`: 确保 session message 的 segments 字段由后端 `TaskCompletionService._build_segments()` 作为唯一构建源，前端流式构建仅用于实时展示，不做持久化合并
- `content-segments-decoupling`: 当前端渲染的消息包含 segments 时，仅渲染时间线，不再单独渲染 content 字段以避免重复

### Modified Capabilities
<!-- No existing spec changes needed - this is a new concern not covered by current specs -->

## Impact

- **后端**: `application/services/task_completion_service.py` — `_build_segments()` 方法重构，消息类型判断统一
- **前端**: `application/services/useChat.ts` — `session:message:saved` 事件处理器简化，删除合并逻辑
- **前端**: `presentation/components/chat/MessageBubble.tsx` — segments 路径下移除 content 回退渲染
- **测试**: 需验证多轮 ReAct、sub-agent、clarify 等场景下 segments 构建正确性
