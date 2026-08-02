## ADDED Requirements

### Requirement: FileBackedSaver persists MemorySaver state as JSON

The system SHALL replace the default `MemorySaver` with a `FileBackedSaver` that extends `MemorySaver` and persists its internal state (`storage`, `writes`, `blobs`) to `checkpointer.json` in the task directory after each `put()` and `put_writes()` operation.

#### Scenario: Checkpointer state saved to JSON file
- **WHEN** LangGraph calls `checkpointer.put()` during graph execution
- **THEN** the checkpointer's `storage`, `writes`, and `blobs` SHALL be serialized to `checkpointer.json`
- **AND** msgpack-encoded binary data SHALL be base64-encoded for JSON compatibility

#### Scenario: Checkpointer state loaded from JSON file
- **WHEN** `FileBackedSaver` is initialized with a path to an existing `checkpointer.json`
- **THEN** `storage`, `writes`, and `blobs` SHALL be restored to the same state they had when saved
- **AND** subsequent `graph.ainvoke(Command(resume=decision), config)` SHALL correctly resume from the interrupt point

#### Scenario: writes captured for interrupt resume
- **WHEN** `tool_execute_node` calls `interrupt()` during graph execution
- **AND** LangGraph calls `checkpointer.put_writes()` with the pending channel writes
- **THEN** the `writes` SHALL be persisted in `checkpointer.json`
- **AND** upon reload, `Command(resume=decision)` SHALL apply the persisted writes to restore state

### Requirement: save_checkpoint_node saves checkpointer state before LLM calls

A new graph node `save_checkpoint_node` SHALL be inserted between `context_compact` and `llm_call` in the agent workflow. This node SHALL serialize the current checkpointer state to `checkpointer.json` before each LLM invocation.

#### Scenario: Checkpointer saved before each LLM call
- **WHEN** the graph transitions from `context_compact` to `save_checkpoint_node`
- **THEN** the current `MemorySaver` state SHALL be written to `checkpointer.json`
- **AND** the node SHALL return an empty state update (no side effects on AgentState)

#### Scenario: Graph structure includes save_checkpoint_node
- **WHEN** the agent workflow graph is compiled
- **THEN** the node ordering SHALL be `context_compact → save_checkpoint_node → llm_call`
- **AND** `save_checkpoint_node` SHALL execute before every LLM invocation

### Requirement: Checkpointer state saved on GraphInterrupt

When `GraphInterrupt` is raised (human-in-the-loop confirmation), the system SHALL save the checkpointer state to `checkpointer.json` after LangGraph has populated `writes`.

#### Scenario: Interrupt triggers checkpointer save
- **WHEN** `AgentLoopRunner` catches a `GraphInterrupt` exception
- **AND** the checkpointer's `writes` contain the pending channel updates from the interrupted node
- **THEN** the checkpointer state SHALL be persisted to `checkpointer.json`
- **AND** the file SHALL contain the `writes` needed for `Command(resume=)` recovery

### Requirement: Approval endpoint resumes from checkpointer.json after restart

After a process restart, the `/approvals` endpoint SHALL load the checkpointer state from `checkpointer.json`, rebuild the graph and config, and resume execution with `Command(resume=decision)`.

#### Scenario: Post-restart approval resumes via checkpointer.json
- **WHEN** a user submits an approval decision after process restart
- **AND** `GraphResumeManager` has no pending context (lost on restart)
- **AND** `checkpointer.json` exists in the task directory
- **THEN** the system SHALL load the checkpointer state from file
- **AND** rebuild the compiled graph via `AgentWorkflowBuilder.build()`
- **AND** rebuild config with `llm`, `event_emitter`, `tool_registry` from dependency injection
- **AND** call `graph.ainvoke(Command(resume=decision), config)`
- **AND** the graph SHALL resume from the `interrupt()` point

#### Scenario: In-process approval still uses GraphResumeManager
- **WHEN** a user submits an approval decision while the process is still alive
- **AND** `GraphResumeManager` has the pending context
- **THEN** the system SHALL use `GraphResumeManager` for resume (no file reload needed)
- **AND** the behavior SHALL be identical to the current implementation

### Requirement: SSE reconnection resumes RUNNING task from checkpointer

When a client reconnects to a RUNNING task via SSE, the system SHALL attempt to load the checkpointer state from `checkpointer.json` and resume graph execution.

#### Scenario: RUNNING task resumed via checkpointer on reconnect
- **WHEN** a client connects to SSE stream for a RUNNING task
- **AND** `checkpointer.json` exists in the task directory
- **THEN** the system SHALL load the checkpointer state
- **AND** rebuild the graph and config
- **AND** execute `graph.ainvoke(state, config)` in background
- **AND** stream new events to the SSE connection

#### Scenario: RUNNING task without checkpointer only replays events
- **WHEN** a client connects to SSE stream for a RUNNING task
- **AND** no `checkpointer.json` exists
- **THEN** the system SHALL replay existing events from `events.jsonl`
- **AND** SHALL NOT attempt to resume graph execution

### Requirement: AgentState checkpoints retained for debugging

The existing `checkpoints/turn_N.json` AgentState snapshots SHALL be retained as auxiliary files for debugging and inspection. They SHALL NOT be used for graph resume (which is handled exclusively by `checkpointer.json`).

#### Scenario: AgentState checkpoint still written alongside checkpointer.json
- **WHEN** graph execution completes normally
- **THEN** both `checkpointer.json` (for resume) and `checkpoints/turn_N.json` (for debugging) SHALL be written
- **AND** the resume flow SHALL use only `checkpointer.json`

### Requirement: Resume metadata stored alongside checkpointer

A `resume_meta.json` file SHALL be stored alongside `checkpointer.json`, containing the parameters needed to rebuild `config["configurable"]` after a restart.

#### Scenario: Resume metadata contains required config parameters
- **WHEN** a task execution begins
- **THEN** `resume_meta.json` SHALL be written with `agent_id`, `session_id`, `model`, `workspace`, `max_turns`
- **AND** these parameters SHALL be sufficient to rebuild the graph config for resume
