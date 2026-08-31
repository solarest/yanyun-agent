# Local Agent State Recovery Design

## Goal

Remove the application-owned LangGraph checkpoint recovery path and restore unfinished agent work from task-local state files instead. Agent state is dumped after every completed loop or tool execution, and reloaded to continue work after a process restart.

## Scope

This change replaces the recovery implementation built around `MemorySaver`, `FileBackedSaver`, `save_checkpoint_node`, and `GraphResumeManager`. LangGraph remains the execution engine; its private checkpointer state is no longer serialized, loaded, or used to resume a task.

The existing task directory, event JSONL stream, deferred user-message persistence, and final message persistence remain unchanged.

## Storage Format

Each task continues to use `storage/sessions/<session_id>/<task_id>/`. Agent recovery data is stored only in numbered JSON snapshots:

```
checkpoints/
  turn_<N>.json
```

Each snapshot contains:

- a JSON-safe `AgentState` payload;
- its completed turn number and write timestamp;
- a `resume_status` of `running` or `awaiting_confirmation`;
- when awaiting confirmation, the pending tool call ID, tool name, and input.

Snapshots are written atomically: serialize to a sibling temporary file, flush it, and replace the target snapshot. A corrupt or incomplete latest snapshot is ignored in favor of the newest readable snapshot.

## Execution and Recovery Flow

The normal graph has no `save_checkpoint` node and compiles without an application-managed LangGraph checkpointer. A local-state persistence node receives the merged `AgentState` immediately after each completed tool execution and writes the snapshot; the runner owns terminal snapshots and restart orchestration.

1. After a tool execution returns, the local-state persistence node writes the resulting state as `turn_N.json`.
2. Before an interrupted task is made available for confirmation, the runner writes a snapshot with `resume_status=awaiting_confirmation` and the pending call.
3. On normal completion, cancellation, or failure, the runner writes a final state snapshot.
4. For a running task found after a restart or reconnection, the runner loads the newest usable snapshot, rebuilds ordinary runtime dependencies, and invokes a fresh graph with that state. It does not deserialize LangGraph internals or repeat completed tools.

Snapshots are a recovery boundary after a completed tool action or a completed loop. A process failure during an in-flight LLM request or tool invocation resumes from the preceding snapshot; the unfinished external action may be retried.

## Confirmation Flow

Pending confirmations are persisted as explicit application data rather than LangGraph `interrupt()` writes.

- On approval, load the pending snapshot, execute the recorded tool once, append its result to `AgentState`, clear the pending record, dump the new snapshot, then invoke a fresh graph for subsequent work.
- On rejection, append a rejected result to `AgentState`, clear the pending record, dump it, then invoke a fresh graph so the model can respond or choose another action.
- The same route works before and after process restart. It no longer uses `Command(resume=...)`, `ResumeContext`, or an in-memory manager.

## Removed Components

Delete the following application-owned LangGraph recovery artifacts and their tests:

- `infrastructure/agent/file_backed_saver.py`
- `infrastructure/agent/save_checkpoint_node.py`
- `infrastructure/agent/graph_resume_manager.py`
- `checkpointer.json` and `resume_meta.json` generation and loading
- graph compilation helpers that accept or install a checkpointer

The `/approvals` route delegates to the local-state recovery service instead of a graph resume manager.

## Errors and Compatibility

If no usable snapshot exists, a running task is replay-only and is not restarted automatically. If the latest snapshot is unreadable, recovery falls back to the latest readable earlier snapshot. Recovery errors mark the task failed and emit the existing failure event.

No SSE event schema, database schema, or public approval endpoint contract changes. Existing legacy `checkpointer.json` files are ignored; no migration is required.

## Test Strategy

Use test-first implementation to verify:

1. snapshots round-trip and select the newest readable state;
2. state is dumped at tool-completion and terminal lifecycle points;
3. a restored task resumes from the local state without instantiating a LangGraph checkpointer;
4. approved and rejected persisted confirmations execute or record the expected outcome after a simulated restart;
5. removed recovery modules are no longer imported by the application.
