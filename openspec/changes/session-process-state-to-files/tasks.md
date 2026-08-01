## 1. Session file storage infrastructure

- [ ] 1.1 Create `application/services/session_file_storage.py` — `SessionFileStorage` service with methods: `create_task_dir()`, `append_event()`, `read_events()`, `write_user_msg()`, `read_user_msg()`, `write_checkpoint()`, `read_latest_checkpoint()`, `write_tool_result_file()`
- [ ] 1.2 Implement directory structure: `storage/sessions/<session_id>/<task_id>/` with `events.jsonl`, `checkpoints/`, `user_msg.json`, `meta.json`, `sub_agents/`, `tool_results/`
- [ ] 1.3 Add `storage/sessions/` to `.gitignore`
- [ ] 1.4 Write unit tests for `SessionFileStorage` (create dir, append event, read events with seek, write/read user_msg, checkpoint round-trip)

## 2. StreamEventService refactor — file-backed event storage

- [ ] 2.1 Refactor `StreamEventService.emit()` to append events to `events.jsonl` instead of `sse_events` table
- [ ] 2.2 Keep in-memory subscriber queue for live SSE push (unchanged)
- [ ] 2.3 Refactor `StreamEventService._replay_events()` to read from `events.jsonl` with Last-Event-ID incremental support
- [ ] 2.4 Remove `sse_events` DB persistence from `StreamEventService`
- [ ] 2.5 Write unit tests for event emit → file, replay from file

## 3. Remove sse_events database artifacts

- [ ] 3.1 Delete `EventModel` from `infrastructure/database/models/agent_model.py`
- [ ] 3.2 Delete `SqliteEventRepository` (`infrastructure/repositories/sqlite_event_repo.py`)
- [ ] 3.3 Remove `sse_events` table creation from `init_db()`
- [ ] 3.4 Remove all imports and usages of `EventModel`, `EventRepo` across codebase
- [ ] 3.5 Run full test suite to catch missing references

## 4. User message deferred persistence

- [ ] 4.1 In `SendMessageUseCase.execute()`, replace `message_repo.add(user_message)` with `file_storage.write_user_msg(task_dir, message)`
- [ ] 4.2 In `TaskCompletionService.finalize()`, read `user_msg.json` and persist user `SessionMessage` alongside assistant message in same transaction
- [ ] 4.3 Update `HistoryLoader` to handle case where user message exists in file but not yet in DB (graceful fallback)
- [ ] 4.4 Write integration test: user message → task execute → finalize → both messages in DB; task cancel → no user message in DB

## 5. Checkpoint mechanism

- [ ] 5.1 Implement `AgentState` serialization helper — convert LangChain messages to dict and back
- [ ] 5.2 Add checkpoint save logic in `AgentLoopLifecycle` — save after each `tool_execute_node` return (before next `llm_call_node`)
- [ ] 5.3 Add final checkpoint save on graph END (when LLM returns no tool calls)
- [ ] 5.4 Implement checkpoint load and graph resume logic in `AgentLoopContext` or `AgentLoopRunner`
- [ ] 5.5 Write unit tests: checkpoint save/load round-trip, resume from mid-execution state

## 6. GraphResumeManager removal

- [ ] 6.1 Refactor `/approvals` endpoint to read AgentState from checkpoint file instead of `GraphResumeManager`
- [ ] 6.2 Delete `GraphResumeManager` and `ResumeContext`
- [ ] 6.3 Update `AgentLoopLifecycle` interrupt branch — remove `ResumeContext` registration
- [ ] 6.4 Write test: interrupt → save checkpoint → resume with approval → graph continues

## 7. Tool output truncation — three-path implementation

- [ ] 7.1 SSE live push truncation: apply `truncate_tool_output()` in `_execute_single_tool()` before SSE emission (keep `result_dict` full for AgentState)
- [ ] 7.2 `events.jsonl`: write full untruncated output (no change needed — file storage handles full data)
- [ ] 7.3 DB `tool_results`: in `TaskCompletionService.finalize()`, truncate output in JSON column + write complete output to `tool_results/<tool_call_id>.txt` + add `full_result_ref` field
- [ ] 7.4 Update `domain/services/tool_output_limits.py` with `truncate_tool_output_for_db()` function (includes `full_result_ref`)
- [ ] 7.5 Write unit tests: each path verified independently

## 8. Sub-agent file storage

- [ ] 8.1 In sub-agent runtime (`sub_agent_runtime.py`), create sub-agent directory under parent task `sub_agents/<sub_task_id>/`
- [ ] 8.2 Sub-agent `StreamEventService` writes to sub-agent's `events.jsonl`, forwards to parent SSE via `ProxyEventEmitter`
- [ ] 8.3 Sub-agent checkpoint support: save checkpoint in sub-agent's `checkpoints/` directory
- [ ] 8.4 Write test: sub-agent events written to own file, also forwarded to parent stream

## 9. SSE reconnection flow

- [ ] 9.1 Implement COMPLETED task replay: read `events.jsonl` → push all events → close
- [ ] 9.2 Implement RUNNING task replay: read `events.jsonl` (respect Last-Event-ID) → load checkpoint → resume graph → push live events
- [ ] 9.3 Remove `sse_events` table query from reconnection path
- [ ] 9.4 Write integration test: disconnect → reconnect → events replayed → graph continues

## 10. Integration & cleanup

- [ ] 10.1 Run full backend test suite, fix regressions
- [ ] 10.2 Manual end-to-end test: send message → execute with tool calls → disconnect → reconnect → verify full event history replayed
- [ ] 10.3 Manual resume test: interrupt (confirmation) → restart server → reconnect → approve → verify execution continues
- [ ] 10.4 Verify DB schema: no `sse_events` table, `session_messages` has user+assistant rows after finalize only
- [ ] 10.5 Verify file structure on disk matches expected layout
