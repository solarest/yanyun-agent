## ADDED Requirements

### Requirement: AgentState checkpoint saved after each ReAct turn

The system SHALL save a complete AgentState snapshot to a local checkpoint file after each ReAct turn completes (tool_execute_node returns, before next llm_call_node begins).

#### Scenario: Checkpoint saved after successful tool execution
- **WHEN** `tool_execute_node` completes execution for the current turn
- **AND** the graph transitions back toward `llm_call_node`
- **THEN** a checkpoint file `checkpoints/turn_N.json` SHALL be written
- **AND** the file SHALL contain the complete serialized AgentState

#### Scenario: Checkpoint saved after llm_call when no tools are invoked
- **WHEN** `llm_call_node` completes and the LLM response contains no tool calls
- **AND** the graph transitions to END
- **THEN** a final checkpoint SHALL be written before the graph terminates

#### Scenario: Checkpoint file naming uses turn number
- **WHEN** a checkpoint is saved for turn N
- **THEN** the file SHALL be named `turn_{N}.json` (e.g., `turn_001.json`, `turn_002.json`)

### Requirement: Agent execution resumes from checkpoint on reconnection

When a client reconnects to a RUNNING task via SSE, the system SHALL restore AgentState from the latest checkpoint file and resume graph execution.

#### Scenario: Resume from latest checkpoint on reconnect
- **WHEN** a client connects to SSE stream for a RUNNING task
- **AND** checkpoint files exist in the task directory
- **THEN** the latest checkpoint (highest turn number) SHALL be loaded as the initial AgentState
- **AND** the graph SHALL continue execution from that state

#### Scenario: New execution when no checkpoint exists
- **WHEN** a client connects to SSE stream for a RUNNING task
- **AND** no checkpoint files exist
- **THEN** the task SHALL be treated as a fresh execution (no recovery possible)
- **AND** the graph SHALL start from the initial state

#### Scenario: Checkpoint serialization handles LangChain message types
- **WHEN** AgentState is serialized to a checkpoint file
- **THEN** LangChain message objects SHALL be converted to their dict representations
- **AND** upon restoration, dict representations SHALL be converted back to message objects

### Requirement: GraphResumeManager removed in favor of checkpoint-based resume

The in-memory `GraphResumeManager` SHALL be removed. Interrupted graph resume SHALL use checkpoint files as the restoration source.

#### Scenario: User approval decision triggers resume from checkpoint
- **WHEN** a user submits an approval decision for a suspended tool
- **THEN** the AgentState SHALL be loaded from the latest checkpoint
- **AND** the approval decision SHALL be injected as a `Command(resume=decision)`
- **AND** the graph SHALL resume from the tool_execute_node that triggered the interrupt
