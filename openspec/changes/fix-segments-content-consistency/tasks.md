## 1. Backend: Unify message type detection in `_build_segments()`

- [ ] 1.1 Extract message type detection into a single `_get_message_kind(msg) -> str` function returning `"ai" | "human" | "system" | "tool" | "unknown"`
- [ ] 1.2 Replace `_is_ai()`, `_is_human_or_system()`, `_is_tool_msg()` internal functions with the unified kind-based dispatch
- [ ] 1.3 Add support for `AIMessageChunk` (from chunk aggregation) in AI message detection
- [ ] 1.4 Write unit tests for `_get_message_kind()` covering: dict with role, dict with tool_calls, AIMessage, AIMessageChunk, HumanMessage, SystemMessage, ToolMessage, unknown types

## 2. Backend: Harden `_build_segments()` tool result matching

- [ ] 2.1 Ensure tool segments default to `toolStatus: "success"` with empty result when no matching tool result exists (currently already done, verify)
- [ ] 2.2 Add defensive check: skip tool_calls with empty or missing `id` (log warning, don't create broken segment)
- [ ] 2.3 Write unit tests for `_build_segments()` covering: single round ReAct, multi-round ReAct, clarify tool output, missing tool result, empty tool call id

## 3. Frontend: Simplify `session:message:saved` handler

- [ ] 3.1 Remove the "longer content wins" heuristic; use saved message's `content` directly
- [ ] 3.2 Remove the "streaming segments preferred over DB segments" logic; use saved message's `segments` directly
- [ ] 3.3 Remove the `thinking_content` merge; use saved message's `thinking_content` directly
- [ ] 3.4 Replace the entire merged object with spread of `savedMsg` only (keep `segments` from saved)
- [ ] 3.5 Verify: during streaming, the placeholder message correctly transitions to saved message without visual regression

## 4. Frontend: Enforce segments-only rendering path

- [ ] 4.1 In `MessageBubble.tsx`, ensure the old path (fixed layout) is never reached when `message.segments` is non-empty
- [ ] 4.2 Add a conditional gate: if `hasSegments` is true, exit the old-path rendering block early (no double render)
- [ ] 4.3 Verify clarify prompt detection works within text segments (MultiClarifyCard/ClarifyCard rendering from segment content)
- [ ] 4.4 Remove unused `displayContent` variable when segments path is active

## 5. Integration & Verification

- [ ] 5.1 Run existing backend tests to confirm no regressions in TaskCompletionService
- [ ] 5.2 Manual test: send a message that triggers multi-round ReAct with tools, verify rendered timeline matches streamed view
- [ ] 5.3 Manual test: page refresh during active streaming, verify recovery shows correct timeline
- [ ] 5.4 Manual test: session with clarify tool, verify clarify card renders correctly in segments path
- [ ] 5.5 Verify session list `last_message_preview` is unaffected (uses `content` field)
