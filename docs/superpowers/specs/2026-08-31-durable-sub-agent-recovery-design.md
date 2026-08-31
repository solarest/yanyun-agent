# Durable Sub-Agent Recovery Design

## Goal

Extend task-local state recovery to sub-agents without reintroducing a LangGraph
checkpointer. A parent agent must be able to resume after a process restart and
continue waiting for an already-created sub-agent; it must never dispatch that
sub-agent again merely because the original in-memory await was lost.

The existing user interaction stays unchanged: sub-agent events and dangerous
tool confirmations are surfaced through the parent task's SSE stream and
`POST /api/tasks/{parent_task_id}/approvals` endpoint.

## Scope

This is a supplement to `2026-08-31-local-agent-state-recovery-design.md`.
It covers the `session_spawn` sub-agent path, child task persistence, parent /
child recovery coordination, and confirmation routing. It does not introduce a
database schema migration, a new public endpoint, or LangGraph checkpoint
serialization.

## Storage Model

Each parent task owns a durable child-task index. Each child remains an
independent task with its own AgentState snapshots:

```text
storage/sessions/<session_id>/<parent_task_id>/
  checkpoints/
    turn_<N>.json
  sub_agents/
    index.json
    <sub_task_id>/
      runtime.json
      checkpoints/
        turn_<N>.json
      events.jsonl
```

All writes to `index.json`, `runtime.json`, and checkpoints use the same
temporary-file, flush, fsync, and replace protocol as normal task snapshots.

### `runtime.json`

`runtime.json` contains only the data needed to rebuild an isolated child
runtime; it is not a second representation of AgentState:

- `sub_task_id`, `parent_task_id`, `session_id`;
- child description, model, workspace, and max turns;
- the child tool allowlist (or an explicit all-allowed value);
- creation timestamp.

This metadata lets the recovery service rebuild the child with
`is_sub_agent=True`, its original tool registry, a parent SSE proxy, and
`persist_session_messages=False`.

### Parent child index

`index.json` is a map keyed by `sub_task_id`. Every entry includes:

- the child directory relative to the parent task directory;
- lifecycle status: `running`, `awaiting_confirmation`, `completed`, `failed`,
  or `cancelled`;
- a result summary or error once terminal;
- `updated_at` and enough runtime identity to validate the corresponding
  `runtime.json`.

The parent AgentState holds a minimal `pending_sub_agents` collection. Each
item identifies an active child by task ID and index location. It does not copy
child messages, tool results, or full state.

## Dispatch and Completion Protocol

`session_spawn` becomes a durable coordinator while preserving its existing
synchronous API to the parent graph.

1. Allocate a stable `sub_task_id` and create the child Task record.
2. Create the child directory and atomically write `runtime.json`.
3. Add a `running` entry to the parent child index.
4. Persist the parent state with that child in `pending_sub_agents`.
5. Start the child runtime, then await that already-identified child.
6. On child completion, write its final snapshot, atomically update the index
   to terminal with its result or error, and return a structured `ToolResult`
   to the existing waiting `session_spawn` call.

The ordering before child execution establishes the recovery boundary: after
step 4 a restart can prove the child was created, so recovery resumes the
existing child instead of invoking `session_spawn` again.

## Recovery Protocol

### Child recovery

Recovery loads the latest readable child snapshot and `runtime.json`, then
rebuilds the graph using child mode. It must preserve:

- `is_sub_agent=True` and the parent task ID;
- the original allowed-tool policy;
- proxied events directed to the parent task;
- disabled normal-session message persistence.

Approval and denial reuse the existing local snapshot continuation logic, but
run against the resolved child task and directory.

### Parent recovery

When a parent snapshot contains `pending_sub_agents`, recovery resolves each
handle in the parent index:

- `completed`: read the durable result and inject the corresponding completed
  `session_spawn` tool result into parent state;
- `failed` or `cancelled`: inject a structured failed tool result;
- `running` or `awaiting_confirmation`: do not create a new child; reattach to
  its existing task lifecycle and wait for its terminal transition.

Once every awaited child is terminal, the parent invokes a fresh graph with the
updated state. It never restores LangGraph execution internals or an old Python
coroutine.

## Confirmation Routing

The public confirmation contract remains parent-task based. On
`POST /api/tasks/{parent_task_id}/approvals`:

1. Read the parent child index and locate an `awaiting_confirmation` child
   whose latest snapshot has the requested tool-call ID.
2. Validate the approval against that child snapshot.
3. Recover the child runtime from its directory and apply the decision once.
4. Persist the child update, then propagate its new lifecycle status to the
   parent index.

The in-memory pending-approval registry remains an optimization for a live
process only; it is never the recovery source of truth.

## Failure and Cancellation Semantics

- Dispatch is idempotent by `sub_task_id`: an existing parent index entry is
  resumed or awaited, never recreated.
- A child completion is durable only after its final snapshot and parent index
  update both succeed. Parent resumption happens afterward.
- A child failure, timeout, or rejected confirmation becomes a structured tool
  failure returned to the parent agent, which may choose its own next action.
- A corrupt child snapshot falls back to the newest readable child snapshot.
  A missing or corrupt parent index/runtime document is a deterministic
  recovery failure; the system must not guess and re-dispatch work.
- Cancelling a parent cancels active child runtimes, records `cancelled` in the
  index, and prevents late child callbacks from resuming the parent.
- Session-level `allow_all` stays in memory. It does not survive a process
  restart; a previously persisted single pending confirmation remains
  actionable after restart.

## Testing Strategy

Test the feature before implementation at three boundaries:

1. **Storage:** runtime metadata and parent index are atomically written and
   updated; a corrupted newest child snapshot falls back safely.
2. **Coordinator:** dispatch persists the child handle before starting child
   execution, and simulated parent recovery does not dispatch a second child.
3. **End-to-end behavior:** a parent-task approval locates and resumes a child
   exactly once; recovered child completion wakes the parent with the expected
   structured result; failures and cancellation never resurrect a parent task.

The final integration test uses the real FastAPI approval route and fresh
runtime instances to simulate a process restart, while tool execution is
stubbed to assert exactly-once behavior.
