## ADDED Requirements

### Requirement: Grouped state accessors for AgentState

The system SHALL provide dataclass-based accessor objects (`ControlFields`, `ContextFields`, `ToolFields`, `TaskFields`) that group related `AgentState` fields by responsibility. Each accessor SHALL implement `from_state(state: AgentState) -> Self` for reading and `to_update() -> dict` for writing state updates. The underlying `AgentState` TypedDict structure SHALL remain unchanged.

#### Scenario: Reading control flow fields via ControlFields

- **WHEN** a node calls `cf = ControlFields.from_state(state)`
- **THEN** `cf.current_turn`, `cf.phase`, `cf.should_end`, `cf.is_complete`, `cf.max_turns` are populated from `state`
- **AND** default values are used for any missing fields

#### Scenario: Writing state updates via ControlFields.to_update

- **WHEN** `llm_call_node` sets `cf.current_turn += 1; cf.phase = "thinking"` and returns `cf.to_update()`
- **THEN** the returned dict contains `{"current_turn": N+1, "phase": "thinking", "should_end": False, "is_complete": False, "max_turns": 100}`

### Requirement: ContextFields for context management fields

`ContextFields` SHALL group all context-management-related state: `max_tokens`, `estimate`, `baseline`, `baseline_count`, `compaction_attempts`, `emergency_requested`, `last_strategy`. It SHALL be the primary interface for `context_compact_node` and `llm_call_node` to read and write context window state.

#### Scenario: ContextCompactNode uses ContextFields to read token state

- **WHEN** `context_compact_node.execute()` calls `ctx = ContextFields.from_state(state)`
- **THEN** `ctx.max_tokens`, `ctx.estimate`, `ctx.baseline`, `ctx.emergency_requested` are available as direct attributes
- **AND** the node does not need to reference raw state dict keys like `state.get("context_token_estimate")`

#### Scenario: LLMCallNode updates baseline via ContextFields

- **WHEN** `llm_call_node` extracts `prompt_tokens` from LLM usage metadata
- **THEN** it SHALL update `ContextFields.baseline` and `ContextFields.baseline_count` via `to_update()`
- **AND** the update dict merges into AgentState through LangGraph's standard reducer

### Requirement: ToolFields for tool execution state

`ToolFields` SHALL group tool-related state: `pending`, `results`, `awaiting_input`, `last_executed_ids`, `final_result`. It SHALL be the primary interface for `tool_execute_node` to read pending tool calls and write execution results.

#### Scenario: ToolExecuteNode reads pending calls via ToolFields

- **WHEN** `tool_execute_node.execute()` calls `tf = ToolFields.from_state(state)`
- **THEN** `tf.pending` returns `state["pending_tool_calls"]`
- **AND** `tf.results` returns `state["tool_results"]`

#### Scenario: ToolExecuteNode writes results via ToolFields

- **WHEN** tool execution completes and `tf.results[tool_call_id] = {...}` is set
- **WHEN** `tf.to_update()` is called and merged into the state update dict
- **THEN** `pending_tool_calls` is cleared, `tool_results` is updated, `last_executed_tool_call_ids` is set

### Requirement: TaskFields for immutable task context

`TaskFields` SHALL group read-only task identification fields: `task_id`, `workspace`, `user_message`, `model`, `is_sub_agent`, `parent_task_id`, `system_prompt`. It SHALL be primarily used during initial state construction in `AgentLoopContext._build_initial_state()`.

#### Scenario: TaskFields used in initial state construction

- **WHEN** `AgentLoopContext._build_initial_state()` constructs the initial `AgentState` dict
- **THEN** it SHALL use `TaskFields(task_id=task.id, workspace=..., ...).to_update()` for task-related fields
- **AND** combine with `ControlFields()`, `ContextFields()`, `ToolFields()` updates via dict unpacking
