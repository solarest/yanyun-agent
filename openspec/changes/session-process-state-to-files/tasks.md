## 1. Session file storage infrastructure

- [x] 1.1 Create `application/services/session_file_storage.py` — `SessionFileStorage` service with methods: `create_task_dir()`, `append_event()`, `read_events()`, `write_user_msg()`, `read_user_msg()`, `write_checkpoint()`, `read_latest_checkpoint()`, `write_tool_result_file()`
- [x] 1.2 Implement directory structure: `storage/sessions/<session_id>/<task_id>/` with `events.jsonl`, `checkpoints/`, `user_msg.json`, `meta.json`, `sub_agents/`, `tool_results/`
- [x] 1.3 Add `storage/sessions/` to `.gitignore`
- [x] 1.4 Write unit tests for `SessionFileStorage` (create dir, append event, read events with seek, write/read user_msg, checkpoint round-trip)

## 2. StreamEventService refactor — file-backed event storage

- [x] 2.1 Refactor `StreamEventService.emit()` to append events to `events.jsonl` instead of `sse_events` table
- [x] 2.2 Keep in-memory subscriber queue for live SSE push (unchanged)
- [x] 2.3 Refactor `StreamEventService._replay_events()` to read from `events.jsonl` with Last-Event-ID incremental support
- [x] 2.4 Remove `sse_events` DB persistence from `StreamEventService`
- [x] 2.5 Write unit tests for event emit → file, replay from file

## 3. Remove sse_events database artifacts

- [x] 3.1 Delete `EventModel` from `infrastructure/database/models/agent_model.py`
- [x] 3.2 Delete `SqliteEventRepository` (`infrastructure/repositories/sqlite_event_repo.py`)
- [x] 3.3 Remove `sse_events` table creation from `init_db()`
- [x] 3.4 Remove all imports and usages of `EventModel`, `EventRepo` across codebase
- [x] 3.5 Run full test suite to catch missing references

## 4. User message deferred persistence

- [x] 4.1 In `SendMessageUseCase.execute()`, replace `message_repo.add(user_message)` with `file_storage.write_user_msg(task_dir, message)`
- [x] 4.2 In `TaskCompletionService.finalize()`, read `user_msg.json` and persist user `SessionMessage` alongside assistant message in same transaction
- [x] 4.3 Update `HistoryLoader` to handle case where user message exists in file but not yet in DB (graceful fallback)
- [ ] 4.4 Write integration test: user message → task execute → finalize → both messages in DB; task cancel → no user message in DB

## 5. Checkpoint mechanism

- [x] 5.1 Implement `AgentState` serialization helper — convert LangChain messages to dict and back
- [x] 5.2 Add checkpoint save logic in `AgentLoopLifecycle` — save after each `tool_execute_node` return (before next `llm_call_node`)
- [x] 5.3 Add final checkpoint save on graph END (when LLM returns no tool calls)
- [ ] 5.4 Implement checkpoint load and graph resume logic in `AgentLoopContext` or `AgentLoopRunner`
- [x] 5.5 Write unit tests: checkpoint save/load round-trip, resume from mid-execution state

## 6. GraphResumeManager removal

- [ ] 6.1 Refactor `/approvals` endpoint to read AgentState from checkpoint file instead of `GraphResumeManager`
- [ ] 6.2 Delete `GraphResumeManager` and `ResumeContext`
- [ ] 6.3 Update `AgentLoopLifecycle` interrupt branch — remove `ResumeContext` registration
- [ ] 6.4 Write test: interrupt → save checkpoint → resume with approval → graph continues

## 7. Tool output truncation — three-path implementation

- [x] 7.1 SSE live push truncation: apply `truncate_tool_output()` in `_execute_single_tool()` before SSE emission (keep `result_dict` full for AgentState)
- [x] 7.2 `events.jsonl`: write full untruncated output (no change needed — file storage handles full data)
- [x] 7.3 DB `tool_results`: in `TaskCompletionService.finalize()`, truncate output in JSON column + write complete output to `tool_results/<tool_call_id>.txt` + add `full_result_ref` field
- [x] 7.4 Update `domain/services/tool_output_limits.py` with `truncate_tool_output_for_db()` function (includes `full_result_ref`)
- [x] 7.5 Write unit tests: each path verified independently

## 8. Sub-agent file storage

- [x] 8.1 In sub-agent runtime (`sub_agent_runtime.py`), create sub-agent directory under parent task `sub_agents/<sub_task_id>/`
- [ ] 8.2 Sub-agent `StreamEventService` writes to sub-agent's `events.jsonl`, forwards to parent SSE via `ProxyEventEmitter`
- [x] 8.3 Sub-agent checkpoint support: save checkpoint in sub-agent's `checkpoints/` directory
- [ ] 8.4 Write test: sub-agent events written to own file, also forwarded to parent stream

## 9. SSE reconnection flow

- [x] 9.1 Implement COMPLETED task replay: read `events.jsonl` → push all events → close
- [ ] 9.2 Implement RUNNING task replay: read `events.jsonl` (respect Last-Event-ID) → load checkpoint → resume graph → push live events
- [x] 9.3 Remove `sse_events` table query from reconnection path
- [ ] 9.4 Write integration test: disconnect → reconnect → events replayed → graph continues

## 11. FileBackedSaver — persistent MemorySaver with JSON serialization

- [x] 11.1 Implement `FileBackedSaver` extending `MemorySaver`, overriding `put` / `aput` / `put_writes` to persist state to JSON file
- [x] 11.2 Implement `_save()`: serialize `storage`, `writes`, `blobs` to JSON with base64-encoded msgpack data
- [x] 11.3 Implement `_load()`: restore `storage`, `writes`, `blobs` from JSON file into MemorySaver internal state
- [x] 11.4 Write unit tests: save → load round-trip, writes persistence, empty state
- [ ] 11.5 Replace `_default_checkpointer()` in `workflow_builder.py` to use `FileBackedSaver`

## 12. save_checkpoint_node — graph node for checkpoint persistence

- [x] 12.1 Create `save_checkpoint_node(state, config)` that serializes current checkpointer state to `checkpointer.json`
- [x] 12.2 Insert node into graph: `context_compact → save_checkpoint_node → llm_call`
- [x] 12.3 Pass `task_dir` through `config["configurable"]` so node knows where to write
- [x] 12.4 Write unit test: node saves checkpointer state when graph runs

## 13. GraphInterrupt checkpoint save

- [x] 13.1 In `AgentLoopRunner`, catch `GraphInterrupt` → call `checkpointer.save_to_file(task_dir)` after checkpointer has `writes`
- [x] 13.2 Write unit test: interrupt → checkpointer.json has writes

## 14. Approval resume from checkpointer.json

- [x] 14.1 Create `resume_meta.json` alongside `checkpointer.json` with `agent_id`, `session_id`, `model`, `workspace`
- [ ] 14.2 Implement resume flow in `/approvals` endpoint: load → rebuild graph + config → `graph.ainvoke(Command(resume=decision), config)`
- [ ] 14.3 Write integration test: interrupt → restart → approve → execution completes

## 15. SSE reconnection resume for RUNNING tasks

- [x] 15.1 In SSE stream route, detect RUNNING task → check for `checkpointer.json`
- [ ] 15.2 If exists: load checkpointer + rebuild graph → `graph.ainvoke(state, config)` in background → stream new events
- [x] 15.3 If not exists: replay events only (current behavior)
- [ ] 15.4 Write integration test: reconnect to RUNNING task → execution resumes
