## MODIFIED Requirements

### Requirement: Tool output is truncated at SSE emission point

The system SHALL truncate tool execution outputs exceeding 50KB before emitting them as SSE `tool:result` events. Truncated output SHALL include a `[truncated: N chars → 50KB]` marker.

> **Change**: Previously this also covered DB `sse_events` table writes. Since `sse_events` is removed, truncation for file storage (`events.jsonl`) is NOT applied — only the live SSE push is truncated.

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

#### Scenario: events.jsonl stores full untruncated output
- **WHEN** a tool execution returns output of any size
- **THEN** the output written to `events.jsonl` SHALL be the complete original output
- **AND** truncation SHALL NOT be applied to the file storage path

### Requirement: Tool output is truncated in persisted session messages

The system SHALL truncate tool execution outputs before storing them in `SessionMessage.tool_results` JSON column. Truncated entries SHALL include a `full_result_ref` field pointing to the complete output in local file storage.

#### Scenario: Large tool output persisted as truncated with file reference
- **WHEN** `TaskCompletionService.finalize()` collects tool results for session message persistence
- **THEN** any tool output exceeding 51200 characters SHALL be truncated before storage in the JSON column
- **AND** the truncation marker SHALL be included
- **AND** a `full_result_ref` field SHALL point to `tool_results/<tool_call_id>.txt` containing the complete output

#### Scenario: LangGraph ToolMessage content is NOT truncated
- **WHEN** tool results are converted to `ToolMessage` objects for LangGraph state
- **THEN** the `ToolMessage` content SHALL retain the full un-truncated output
- **AND** only the SSE/DB paths SHALL use truncated output

#### Scenario: Complete tool output written to tool_results file
- **WHEN** a tool output exceeds 51200 characters
- **AND** `TaskCompletionService.finalize()` is called
- **THEN** the complete output SHALL be written to `tool_results/<tool_call_id>.txt` in the task directory
- **AND** the file SHALL be created even if the output is also stored in `events.jsonl`

## REMOVED Requirements

### Requirement: Sub-agent replay does not overwrite persisted messages

> **Reason**: This requirement addressed the `sse_events` table replay issue. With checkpoint-based resume and file-based event storage, the replay mechanism is fundamentally different and this specific guard is no longer needed in its current form. Sub-agent message integrity is instead ensured by the checkpoint-resume flow.
