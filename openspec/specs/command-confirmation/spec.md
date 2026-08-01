# command-confirmation

## Purpose

对 `shell` 工具的执行前人在回路确认闸门：危险命令分类、同步阻塞等待用户决策、
会话级"全部允许"白名单、确认所需的 SSE 事件与 HTTP 端点、前端确认卡。覆盖
顶层 agent、sub-agent 与 team member 的 `shell` 调用。

## Requirements

### Requirement: Dangerous command classification

The system SHALL classify a `shell` tool command as requiring confirmation when it matches a configurable dangerous-command set. The dangerous-command set SHALL be loaded from a configuration file (not hardcoded). Classification SHALL inspect every segment of a compound shell string (pipes / `&&` / `;` / `$()` / subshells) and SHALL flag the command for confirmation if any dangerous token appears in any segment or the raw string.

#### Scenario: Dangerous token triggers confirmation
- **WHEN** the LLM calls `shell` with a command containing `rm -rf`
- **THEN** the command is classified as requiring confirmation

#### Scenario: Safe command requires no confirmation
- **WHEN** the LLM calls `shell` with the command `ls -la`
- **THEN** the command is not classified as requiring confirmation

#### Scenario: Compound shell is scanned
- **WHEN** the LLM calls `shell` with the command `ls && rm -rf build`
- **THEN** the command is classified as requiring confirmation because a dangerous token appears in one segment

#### Scenario: Classification follows configuration
- **WHEN** the dangerous-command set is changed in the configuration file
- **THEN** classification reflects the new set without any code change

### Requirement: Pre-execution blocking confirmation gate

For a `shell` tool call classified as requiring confirmation and not already allowed, the system SHALL suspend execution of the tool call (without terminating the agent turn) and SHALL emit a confirmation request, resuming execution only after the user's decision arrives. The confirmation gate SHALL be ordered outside the tool execution timeout middleware so that the approval wait is not killed by the execution timeout. Approved calls SHALL proceed to execute; denied calls SHALL return a `user_denied` error result to the LLM without aborting the task.

#### Scenario: Dangerous command blocks and prompts
- **WHEN** the LLM calls `shell` with a dangerous command that is not already allowed
- **THEN** the system emits `tool:confirmation_required` and does not execute the command until a decision arrives

#### Scenario: Safe command is not blocked
- **WHEN** the LLM calls `shell` with a command not classified as dangerous
- **THEN** the command executes immediately without any confirmation prompt

#### Scenario: Approval wait is not subject to execution timeout
- **WHEN** the user takes longer than the tool's execution timeout (30s) to respond
- **THEN** the confirmation gate is not killed by the execution timeout

#### Scenario: Approved command executes
- **WHEN** the user chooses allow-once for a pending dangerous command
- **THEN** the suspended `shell` call resumes and executes the command

#### Scenario: Denied command returns error to LLM
- **WHEN** the user chooses deny for a pending dangerous command
- **THEN** the tool returns a `user_denied` error result to the LLM and the task is not aborted

### Requirement: Per-session allow-all allowlist

When the user chooses allow-all for a command category, the system SHALL record that category in a per-session allowlist and SHALL NOT prompt again for commands of that category within the same session. The allowlist SHALL be keyed by command category/pattern (not exact command string) and SHALL NOT persist across sessions or process restarts.

#### Scenario: Allow-all suppresses future prompts
- **WHEN** the user chooses allow-all for the `sudo` category
- **THEN** a subsequent `sudo` command in the same session executes without a confirmation prompt

#### Scenario: Allow-all does not persist across sessions
- **WHEN** a new session begins
- **THEN** commands that were allow-all'd in a previous session still require confirmation

#### Scenario: Allow-once does not add to allowlist
- **WHEN** the user chooses allow-once for a command
- **THEN** a subsequent command of the same category still requires confirmation

### Requirement: Approval decision endpoint

The system SHALL expose an HTTP endpoint that accepts a decision (`allow_once` / `allow_all` / `deny`) for a specific pending confirmation, identified by task id and tool call id, and SHALL resolve the corresponding suspended tool call.

#### Scenario: Valid decision resolves pending call
- **WHEN** a request is POSTed to the approvals endpoint with a known toolCallId and decision `allow_once`
- **THEN** the corresponding suspended tool call resumes

#### Scenario: Unknown toolCallId rejected
- **WHEN** the endpoint receives a toolCallId with no pending confirmation
- **THEN** it returns an error

#### Scenario: Late decision after timeout ignored
- **WHEN** a decision arrives after the approval timeout has auto-denied the call
- **THEN** the decision is rejected because the pending confirmation no longer exists

#### Scenario: Cross-scope pending call is resolvable
- **WHEN** a pending confirmation belongs to a sub-agent's or team member's `shell` call rather than the top-level agent's
- **THEN** the approvals endpoint resolves it by task id and tool call id exactly as for a top-level call, because the pending registry is a single shared instance across all execution scopes and is keyed by the effective (parent) task id that matches the event stream the frontend received the confirmation on

### Requirement: Confirmation-required SSE event

The system SHALL emit a `tool:confirmation_required` SSE event carrying the tool call id, command, risk reason, working directory, and available options, so the frontend can render a confirmation card while the tool is suspended. Task status SHALL remain running (not paused) during the wait.

#### Scenario: Event emitted when gate triggers
- **WHEN** a `shell` call is suspended for confirmation
- **THEN** a `tool:confirmation_required` event is emitted containing the command and toolCallId

#### Scenario: Task stays running while awaiting confirmation
- **WHEN** a tool call is awaiting confirmation
- **THEN** the task status remains running (not set to paused)

### Requirement: Approval timeout auto-deny

The system SHALL automatically deny a pending confirmation if no decision arrives within a configurable timeout (default 5 minutes), returning an `approval_timeout` error result to the LLM and freeing the suspended tool call.

#### Scenario: Timeout auto-denies
- **WHEN** no decision arrives within the configured timeout
- **THEN** the tool returns an `approval_timeout` error result and the suspended call is freed

#### Scenario: Timeout is configurable
- **WHEN** the timeout is set to a different value in configuration
- **THEN** the auto-deny deadline reflects the configured value

### Requirement: Sub-agent and team member coverage

The confirmation gate SHALL apply to `shell` calls made by sub-agents and team members, not only the top-level agent. The scoped tool registries used by sub-agents and team members SHALL be constructed with a confirmation-capable execution pipeline (not the default empty pipeline).

#### Scenario: Sub-agent shell call is gated
- **WHEN** a sub-agent calls `shell` with a dangerous command
- **THEN** the confirmation gate triggers before execution

#### Scenario: Team member shell call is gated
- **WHEN** a team member calls `shell` with a dangerous command
- **THEN** the confirmation gate triggers before execution

### Requirement: Frontend confirmation card

The frontend SHALL render a confirmation card for a pending `tool:confirmation_required` event, displaying the command and risk reason and providing three actions: allow-once / allow-all / deny. The card SHALL post the user's decision to the approvals endpoint keyed by tool call id, and SHALL enter a read-only answered state after a decision is submitted.

#### Scenario: Card renders on event
- **WHEN** the frontend receives a `tool:confirmation_required` event
- **THEN** a confirmation card displays the command and risk reason with three action buttons

#### Scenario: Decision is posted to the endpoint
- **WHEN** the user clicks an action button
- **THEN** the frontend posts the decision to the approvals endpoint carrying the toolCallId

#### Scenario: Card becomes read-only after answer
- **WHEN** a decision has been submitted for a confirmation card
- **THEN** the card enters a read-only answered state and its action buttons are disabled
