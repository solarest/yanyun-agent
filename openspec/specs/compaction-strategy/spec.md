# Compaction Strategy

## Purpose

Provide a pluggable, priority-based compaction strategy framework for managing context window pressure in the Agent Loop. Strategies are independent classes implementing a common interface, allowing new compaction behaviors to be added without modifying existing code.

## Requirements

### Requirement: Pluggable compaction strategies

The system SHALL support a pluggable compaction strategy framework where each strategy is an independent class implementing a common abstract interface (`CompactionStrategy`). Strategies SHALL be registered with a `priority` integer and evaluated in descending priority order. The first strategy whose `should_apply()` evaluates to `True` SHALL be executed.

#### Scenario: Strategy chain evaluation by priority

- **WHEN** `ContextCompactNode` receives `AgentState` with `current_tokens > 60% * max_context_tokens`
- **THEN** `EmergencyCompactStrategy.should_apply()` evaluates first (priority=3), returns `False` (no emergency flag set)
- **AND** `MicroCompactStrategy.should_apply()` evaluates next (priority=2), returns `True`
- **AND** `MicroCompactStrategy.apply()` is executed
- **AND** lower-priority strategies (`SoftPruneStrategy`, `SkipStrategy`) are skipped

#### Scenario: Emergency compaction takes precedence

- **WHEN** `AgentState.emergency_compact_requested` is `True`
- **THEN** `EmergencyCompactStrategy.should_apply()` returns `True` regardless of token count
- **AND** no other strategy is considered

#### Scenario: SkipStrategy as fallback

- **WHEN** `current_tokens <= 40% * max_context_tokens` and no other triggers are active
- **THEN** all other strategies return `False` from `should_apply()`
- **AND** `SkipStrategy` (priority=0) evaluates as the last strategy, returns `True`
- **AND** `SkipStrategy.apply()` returns a no-op `CompactionResult` preserving all messages

### Requirement: Strategy result contract

Each strategy's `apply()` method SHALL return a `CompactionResult` dataclass containing: `strategy` (string identifier), `messages` (processed message list), `token_estimate` (post-compaction token count), `removed_count`, and `baseline_invalidated` flag. The `CompactionResult.to_state_update()` method SHALL convert this into an `AgentState` update dictionary suitable for LangGraph.

#### Scenario: Soft-prune returns baseline_invalidated=True

- **WHEN** `SoftPruneStrategy.apply()` truncates one or more `ToolMessage` contents
- **THEN** returned `CompactionResult.baseline_invalidated` is `True`
- **AND** `to_state_update()` sets `context_token_baseline` to `None`, forcing full token re-estimation on next cycle

#### Scenario: Skip returns baseline_invalidated=False

- **WHEN** `SkipStrategy.apply()` is executed (no messages modified)
- **THEN** returned `CompactionResult.baseline_invalidated` is `False`
- **AND** `to_state_update()` preserves existing `context_token_baseline`

### Requirement: New strategy registration without modifying existing code

Adding a new compaction strategy SHALL require only: (1) creating a new class implementing `CompactionStrategy`, (2) adding it to the strategy list with an appropriate `priority`. No changes to `ContextCompactNode` or existing strategy files SHALL be necessary.

#### Scenario: Adding a new strategy between micro and emergency

- **WHEN** a developer creates `AggressiveCompactStrategy` with `priority=4` in a new file under `compaction/`
- **AND** registers it in the strategy factory
- **THEN** `ContextCompactNode` picks it up automatically via priority-based iteration
- **AND** no other files are modified

### Requirement: Shared compaction utilities

The system SHALL provide shared utility functions for common compaction operations: `compact_messages()` for the common message-preservation + summary injection logic used by micro and emergency compaction, and `SummaryGenerator` for LLM-based context summarization. These utilities SHALL be usable by any strategy without inheritance.

#### Scenario: MicroCompactStrategy uses shared compact_messages

- **WHEN** `MicroCompactStrategy.apply()` needs to preserve `SystemMessage` + 10 recent messages and summarize older ones
- **THEN** it delegates to `compact_messages(messages, keep_recent=10, summary_budget=BUDGET, llm=llm)`
- **AND** `compact_messages` handles `RemoveMessage` insertion, summary injection with timeline position preservation, and message reordering

### Requirement: LLM summary generation as standalone component

The system SHALL provide a `SummaryGenerator` class that encapsulates the LLM call for context summarization. It SHALL accept a configurable `summary_prompt`, budget constraints (`max_input_chars`, `max_token_fraction`), and return the summary text or `None` on failure. Strategies SHALL use `SummaryGenerator` via composition, not by calling LLM directly.

#### Scenario: Summary generation with budget constraint

- **WHEN** `SummaryGenerator.generate(messages, max_tokens, llm)` is called with 100 messages totaling 50000 characters
- **AND** `summary_budget = min(32000, int(max_tokens * 0.05 * 4))` resolves to 25600 chars
- **THEN** the input to LLM is truncated to fit within the budget
- **AND** a `HumanMessage` with truncated content is sent alongside the system `_COMPACTION_SUMMARY_PROMPT`

#### Scenario: Summary generation fallback on LLM failure

- **WHEN** `SummaryGenerator.generate()` encounters an exception from the LLM call
- **THEN** it logs a warning and returns `None`
- **AND** the calling strategy falls back to pure `RemoveMessage` (trim-only) behavior
