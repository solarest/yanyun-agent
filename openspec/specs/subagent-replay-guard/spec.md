# subagent-replay-guard

## Purpose

TBD — prevents duplicate streaming placeholder messages when recovering an active stream (page refresh or reconnect) by checking the actual message list for persisted sub-agent messages before creating new placeholders.

## Requirements

### Requirement: Sub-agent replay guard checks message list before creating placeholder

The `connectSubAgentStream` function SHALL consult the actual message list state, in addition to `subAgentMessagesRef`, to determine whether a placeholder needs to be created for a sub-agent.

#### Scenario: Message list has persisted sub-agent message checked before placeholder creation
- **WHEN** `connectSubAgentStream()` is called with a `subTaskId`
- **AND** the message list contains a message with `id === subTaskId`
- **THEN** the function SHALL NOT create a new placeholder
- **AND** the existing message SHALL NOT be replaced

#### Scenario: SubAgentMessagesRef already tracks the sub-agent
- **WHEN** `connectSubAgentStream()` is called with a `subTaskId`
- **AND** `subAgentMessagesRef` already contains the `subTaskId`
- **THEN** the function SHALL return immediately without creating any message

#### Scenario: No existing state found creates new placeholder
- **WHEN** `connectSubAgentStream()` is called with a `subTaskId`
- **AND** neither `subAgentMessagesRef` nor the message list contains the `subTaskId`
- **THEN** the function SHALL create a new streaming placeholder message
- **AND** add the `subTaskId` to `subAgentMessagesRef`
