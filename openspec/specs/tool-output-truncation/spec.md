# tool-output-truncation

## Purpose

TBD — prevents oversized tool execution outputs from bloating SSE events and database storage by truncating outputs exceeding 50KB at the SSE emission point and in persisted session messages.

## Requirements

### Requirement: Tool output is truncated at SSE emission point

The system SHALL truncate tool execution outputs exceeding 50KB before emitting them as SSE `tool:result` events. Truncated output SHALL include a `[truncated: N chars → 50KB]` marker.

#### Scenario: Large tool output is truncated before SSE push
- **WHEN** a tool execution returns output longer than 51200 characters
- **THEN** the SSE `tool:result` event payload SHALL contain output truncated to 51200 characters
- **AND** the output SHALL end with a truncation marker indicating original and truncated size

#### Scenario: Normal tool output passes through unchanged
- **WHEN** a tool execution returns output shorter than 51200 characters
- **THEN** the SSE `tool:result` event payload SHALL contain the complete original output

#### Scenario: Tool error messages are not truncated
- **WHEN** a tool execution returns an error message
- **THEN** the error SHALL NOT be truncated (errors are typically short)

### Requirement: Tool output is truncated in persisted session messages

The system SHALL truncate tool execution outputs before storing them in `SessionMessage.tool_results` JSON column and in `sse_events` event store.

#### Scenario: Large tool output persisted as truncated
- **WHEN** `TaskCompletionService.finalize()` collects tool results for session message persistence
- **THEN** any tool output exceeding 51200 characters SHALL be truncated before storage
- **AND** the truncation marker SHALL be included

#### Scenario: LangGraph ToolMessage content is NOT truncated
- **WHEN** tool results are converted to `ToolMessage` objects for LangGraph state
- **THEN** the `ToolMessage` content SHALL retain the full un-truncated output
- **AND** only the SSE/DB paths SHALL use truncated output

### Requirement: Sub-agent replay does not overwrite persisted messages

When recovering an active stream (page refresh or reconnect), the frontend SHALL check the actual message list for existing persisted sub-agent messages before creating streaming placeholders.

#### Scenario: Replayed sub_agent:started skips already-persisted sub-agent
- **WHEN** a `sub_agent:started` SSE event is replayed for a sub_task_id
- **AND** the message list already contains a message with `id === sub_task_id` and `status !== 'streaming'`
- **THEN** no new placeholder message SHALL be created
- **AND** the existing persisted message SHALL remain unchanged

#### Scenario: Sub_agent:started during live streaming creates placeholder
- **WHEN** a `sub_agent:started` SSE event arrives during live streaming (not replay)
- **AND** no message with `id === sub_task_id` exists in the message list
- **THEN** a new streaming placeholder message SHALL be created for the sub-agent
