## 1. Backend: Create tool output truncation utility

- [x] 1.1 Create `domain/services/tool_output_limits.py` with `MAX_TOOL_OUTPUT_SIZE = 51200` constant and `truncate_tool_output(output: str) -> str` function
- [x] 1.2 Write unit tests for `truncate_tool_output()`: output under limit unchanged, output over limit truncated with marker, empty string, None handling

## 2. Backend: Apply truncation in tool execution node

- [x] 2.1 In `tool_execute_node.py:_execute_single_tool()`, truncate `result.output` before building `result_dict["output"]` for SSE emission (line ~89-93)
- [x] 2.2 Verify: full `result.output` is still available to the tool execution pipeline before truncation
- [x] 2.3 Write unit test: tool with large output → SSE event payload is truncated

## 3. Backend: Apply truncation in TaskCompletionService

- [x] 3.1 In `TaskCompletionService.finalize()`, truncate tool output before appending to `all_tool_results` (line ~116)
- [x] 3.2 Verify: ToolMessage content passed to LangGraph is NOT truncated (only `all_tool_results` for DB/SSE is)
- [x] 3.3 Write unit test: `finalize()` with large tool results → saved message has truncated tool_results

## 4. Frontend: Sub-agent replay guard in connectSubAgentStream

- [x] 4.1 Add `messages` parameter (or ref) to `connectSubAgentStream` to access current message list state
- [x] 4.2 Before creating placeholder, check if message list already contains `id === subTaskId` with `status !== 'streaming'`
- [x] 4.3 If persisted message found, skip placeholder creation and add to `subAgentMessagesRef` to prevent future duplicates in same session
- [x] 4.4 Keep existing `subAgentMessagesRef.has()` check as first guard

## 5. Integration & Verification

- [x] 5.1 Run all backend tests to confirm no regressions
- [ ] 5.2 Manual test: tool that outputs > 50KB (e.g., `cat` a large file), verify SSE and DB contain truncated version
- [ ] 5.3 Manual test: page refresh during active sub-agent execution, verify sub-agent messages are preserved not overwritten
- [x] 5.4 Verify truncation marker format matches frontend display expectations
