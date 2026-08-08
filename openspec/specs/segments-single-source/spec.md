# segments-single-source

## Purpose

确保 session message 的 `segments` 字段由后端 `TaskCompletionService._build_segments()` 作为唯一构建源,前端流式构建仅用于实时展示,`session:message:saved` 事件到达后以保存的消息整体替换,不做字段级合并启发式。

## Requirements

### Requirement: Backend is the single source of truth for message segments

The system SHALL construct the `segments` field of a saved `SessionMessage` exclusively in the backend `TaskCompletionService._build_segments()` method. The frontend streaming-built segments are ephemeral and SHALL be discarded when the `session:message:saved` event arrives.

#### Scenario: Saved message segments replace streaming segments
- **WHEN** frontend receives a `session:message:saved` SSE event
- **THEN** the placeholder streaming message SHALL be replaced with the saved message's fields (segments, content, thinking_content, tool_calls, tool_results) without field-level merging heuristics

#### Scenario: Streaming segments are for real-time display only
- **WHEN** an agent task is streaming
- **THEN** the frontend SHALL continue to incrementally build segments for real-time timeline rendering
- **AND** these streaming-built segments SHALL NOT be used as the source of truth after the saved message arrives

### Requirement: Robust message type detection in segments builder

The `_build_segments()` method SHALL use a single, unified message type detection function to determine whether a LangGraph message is an AI message (yields text and tool segments), a human/system message (skipped), or a tool message (skipped, tool results matched via tool_call_id).

#### Scenario: Dict-format messages with tool_calls are recognized as AI messages
- **WHEN** `_build_segments()` encounters a dict message with `tool_calls` field or `role: "assistant"`
- **THEN** the message SHALL be treated as an AI message and its content and tool_calls SHALL be added to segments

#### Scenario: LangChain AIMessage objects are recognized as AI messages
- **WHEN** `_build_segments()` encounters a LangChain `AIMessage` or `AIMessageChunk` object
- **THEN** the message SHALL be treated as an AI message and its content and tool_calls SHALL be added to segments

#### Scenario: Human and system messages are skipped
- **WHEN** `_build_segments()` encounters a `HumanMessage`, `SystemMessage`, or dict with `role: "user"` or `role: "system"`
- **THEN** the message SHALL be skipped and SHALL NOT contribute to segments

### Requirement: Tool results are correctly matched to tool segments

Each tool segment in `_build_segments()` output SHALL be matched with its corresponding tool result via `tool_call_id`, and the segment SHALL include `toolStatus` and `toolResult` fields reflecting the actual execution outcome.

#### Scenario: Tool result matched by tool_call_id
- **WHEN** a tool_call with id "abc123" has a corresponding tool_result
- **THEN** the tool segment SHALL have `toolStatus: "success"` and `toolResult` containing the output

#### Scenario: Tool call without matching result defaults to success
- **WHEN** a tool_call has no matching tool_result in all_tool_results
- **THEN** the tool segment SHALL default to `toolStatus: "success"` and `toolResult: ""`
