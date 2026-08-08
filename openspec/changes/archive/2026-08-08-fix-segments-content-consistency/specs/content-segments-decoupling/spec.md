## ADDED Requirements

### Requirement: Segments-based rendering suppresses standalone content rendering

When an assistant message has a non-empty `segments` field, the MessageBubble component SHALL render only the timeline view (segments), and SHALL NOT render `content` as a separate text block, because all text content is already represented by text-type segments in the timeline.

#### Scenario: Message with segments renders timeline only
- **WHEN** an assistant message has `segments: [{type: "text", content: "Hello"}, {type: "tool", content: "read_file", ...}]`
- **THEN** the component SHALL render the timeline (text block "Hello" followed by tool card)
- **AND** the `content` field SHALL NOT be rendered as a separate Markdown block

#### Scenario: Message without segments falls back to content rendering
- **WHEN** an assistant message has empty or missing `segments` field
- **THEN** the component SHALL fall back to rendering `content` as a Markdown block
- **AND** tool_calls and thinking_content SHALL also be rendered in their respective sections

#### Scenario: Streaming message with ephemeral segments renders timeline
- **WHEN** an assistant message is in `streaming` status with incrementally-built segments
- **THEN** the component SHALL render the timeline using the current streaming segments
- **AND** SHALL NOT show `content` as fallback even during streaming

### Requirement: Content field is preserved for non-rendering purposes

The `content` field of `SessionMessage` SHALL remain populated as a plain-text summary of the assistant's response, and SHALL be used for session list previews and search functionality regardless of whether segments exist.

#### Scenario: Last message preview uses content field
- **WHEN** the session list displays `last_message_preview`
- **THEN** it SHALL use the `content` field (truncated) regardless of whether the message has segments

#### Scenario: Search across messages uses content field
- **WHEN** searching messages by text
- **THEN** the `content` field SHALL be searchable even when segments exist
