## ADDED Requirements

### Requirement: Session process state stored as local files

The system SHALL store all agent execution process state as local files under a per-task directory, replacing the `sse_events` database table.

#### Scenario: Task process directory created on execution start
- **WHEN** a new task execution begins
- **THEN** a directory `storage/sessions/<session_id>/<task_id>/` SHALL be created
- **AND** the directory SHALL contain `meta.json` with task metadata (created_at, agent_id, session_id)

#### Scenario: SSE events written to events.jsonl
- **WHEN** any SSE event is emitted during task execution
- **THEN** the event SHALL be appended as a JSON line to `events.jsonl`
- **AND** each line SHALL include `seq`, `type`, `data`, and `timestamp` fields

#### Scenario: User message deferred to local file
- **WHEN** a user sends a message to a session
- **THEN** the user message content SHALL be written to `user_msg.json` in the task directory
- **AND** the message SHALL NOT be written to the `session_messages` database table at this time

### Requirement: Finalize writes user and assistant messages atomically

The `TaskCompletionService.finalize()` method SHALL write both the user message and the assistant response message to the `session_messages` table in a single database transaction.

#### Scenario: Normal completion persists both messages atomically
- **WHEN** agent execution completes successfully
- **THEN** the user message from `user_msg.json` SHALL be persisted to `session_messages`
- **AND** the assistant message (content, thinking, tool_calls, tool_results) SHALL be persisted to `session_messages`
- **AND** both inserts SHALL occur within the same database transaction

#### Scenario: Execution failure leaves no orphan messages
- **WHEN** agent execution fails or is cancelled before finalize
- **THEN** no user message row SHALL exist in `session_messages` for that task
- **AND** `user_msg.json` SHALL be retained for debugging

### Requirement: Sub-agent process state in independent file directory

Sub-agent executions SHALL store their process state in a directory nested under the parent task: `sub_agents/<sub_task_id>/`.

#### Scenario: Sub-agent creates own events.jsonl
- **WHEN** a sub-agent is spawned during parent task execution
- **THEN** a directory `sub_agents/<sub_task_id>/` SHALL be created under the parent task directory
- **AND** the sub-agent's SSE events SHALL be written to its own `events.jsonl`

#### Scenario: Sub-agent SSE events forwarded to parent stream
- **WHEN** a sub-agent emits an SSE event
- **THEN** the event SHALL be appended to the sub-agent's `events.jsonl`
- **AND** the event SHALL be forwarded to the parent task's live SSE connection via `ProxyEventEmitter`

### Requirement: SSE replay reads from local files

The SSE stream endpoint SHALL replay historical events from the local `events.jsonl` file instead of the `sse_events` database table.

#### Scenario: Completed task replays full event history
- **WHEN** a client connects to SSE stream for a COMPLETED task
- **THEN** all events from `events.jsonl` SHALL be replayed in sequence order
- **AND** the connection SHALL close after replay completes

#### Scenario: Running task replays and continues streaming
- **WHEN** a client connects to SSE stream for a RUNNING task
- **THEN** existing events from `events.jsonl` SHALL be replayed (supporting Last-Event-ID)
- **AND** new live events SHALL be pushed as they arrive

### Requirement: sse_events database table removed

The `sse_events` database table and all associated ORM models and repository implementations SHALL be removed from the codebase.

#### Scenario: No sse_events writes during execution
- **WHEN** any task executes
- **THEN** no rows SHALL be inserted into any `sse_events` table

#### Scenario: sse_events table dropped from schema
- **WHEN** the application starts and runs schema initialization
- **THEN** the `sse_events` table SHALL NOT exist in the database schema
