# Durable Sub-Agent Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make an already-dispatched sub-agent recoverable from local files so a restarted parent task continues waiting for it without dispatching duplicate work.

**Architecture:** Keep every child as an independent Task with its own AgentState snapshot. `SessionFileStorage` persists child runtime metadata and a parent-owned child index; `session_spawn` records a parent child handle before execution. The runner restores child-mode dependencies from that metadata and resolves a completed child into the original parent tool call before invoking a fresh parent graph.

**Tech Stack:** Python 3.14, FastAPI, LangGraph StateGraph without checkpointers, LangChain messages, pytest, local JSON files.

**Spec:** `docs/superpowers/specs/2026-08-31-durable-sub-agent-recovery-design.md`

## Global Constraints

- Never serialize, load, or use `MemorySaver`, `Command(resume=...)`, or an in-memory graph-resume registry.
- The parent-facing SSE and `POST /api/tasks/{parent_task_id}/approvals` API contract stay unchanged.
- A child AgentState is stored only in `sub_agents/<sub_task_id>/checkpoints/`; the parent stores a small child handle, never copies child messages or tool results.
- Write `runtime.json`, `index.json`, and checkpoints atomically with a sibling temporary file, flush, fsync, and replace.
- Once a child handle is durable, restart recovery must reuse that `sub_task_id` and never call `session_spawn` to create a replacement child.
- Child recovery must rebuild `is_sub_agent=True`, the original allowed-tool policy, parent event proxy, and `persist_session_messages=False`.
- Missing or invalid child metadata is a deterministic recovery failure; do not infer a new child task.
- Every behavior change begins with a focused failing test. Keep the existing public DTOs and SSE event names.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `backend/src/application/services/session_file_storage.py` | Atomic child runtime/index reads and writes; no workflow logic. |
| `backend/src/domain/aggregates/agent/agent_state.py` | Typed parent child-handle state. |
| `backend/src/application/services/sub_agent_recovery.py` | Purely application-level dispatch records, terminal-index updates, and parent-state result application. |
| `backend/src/application/services/agent_loop_context.py` | Initializes the typed parent child-handle state. |
| `backend/src/infrastructure/tools/builtin/session_spawn.py` | Persists the durable dispatch record before starting and awaiting a child. |
| `backend/src/application/services/agent_loop_runner.py` | Rebuilds child-mode runtime from metadata and resumes a parent only after child results are durable. |
| `backend/src/presentation/routes/tasks.py` | Resolves a parent approval to an awaiting child snapshot. |

### Task 1: Atomically persist child runtime metadata and parent index

**Files:**
- Modify: `backend/src/application/services/session_file_storage.py`
- Test: `backend/tests/unit/application/services/test_session_file_storage.py`

**Interfaces:**
- Produces `write_sub_agent_runtime(parent_task_dir: Path, runtime: dict) -> Path`.
- Produces `read_sub_agent_runtime(parent_task_dir: Path, sub_task_id: str) -> dict | None`.
- Produces `upsert_sub_agent_index(parent_task_dir: Path, entry: dict) -> dict`.
- Produces `read_sub_agent_index(parent_task_dir: Path) -> dict[str, dict]`.
- Produces `find_pending_sub_agent(parent_task_dir: Path, tool_call_id: str) -> dict | None`.

- [ ] **Step 1: Write failing storage tests**

```python
def test_sub_agent_runtime_round_trips_atomically(tmp_path):
    storage = SessionFileStorage(base_path=str(tmp_path))
    parent_dir = storage.create_task_dir("session-1", "parent-1")
    runtime = {
        "sub_task_id": "sub-1", "parent_task_id": "parent-1",
        "session_id": "session-1", "description": "research",
        "model": "model-1", "workspace": "/tmp/work", "max_turns": 50,
        "allowed_tools": ["web_search"], "created_at": "2026-08-31T00:00:00+00:00",
    }

    path = storage.write_sub_agent_runtime(parent_dir, runtime)

    assert path == parent_dir / "sub_agents" / "sub-1" / "runtime.json"
    assert storage.read_sub_agent_runtime(parent_dir, "sub-1") == runtime
    assert not path.with_suffix(".json.tmp").exists()


def test_child_index_upsert_and_pending_lookup(tmp_path):
    storage = SessionFileStorage(base_path=str(tmp_path))
    parent_dir = storage.create_task_dir("session-1", "parent-1")
    storage.upsert_sub_agent_index(parent_dir, {
        "sub_task_id": "sub-1", "tool_call_id": "call-1",
        "relative_dir": "sub_agents/sub-1", "status": "awaiting_confirmation",
        "updated_at": "2026-08-31T00:00:00+00:00",
    })

    found = storage.find_pending_sub_agent(parent_dir, "call-1")

    assert storage.read_sub_agent_index(parent_dir)["sub-1"]["status"] == "awaiting_confirmation"
    assert found["sub_task_id"] == "sub-1"
```

- [ ] **Step 2: Verify the tests fail**

Run: `cd backend && uv run pytest tests/unit/application/services/test_session_file_storage.py -q`

Expected: FAIL because child runtime/index APIs do not exist.

- [ ] **Step 3: Add a shared atomic JSON writer and child-specific storage methods**

```python
def _write_json_atomically(self, path: Path, payload: dict) -> Path:
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    with open(temporary_path, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.flush()
        os.fsync(file.fileno())
    temporary_path.replace(path)
    return path

def upsert_sub_agent_index(self, parent_task_dir: Path, entry: dict) -> dict:
    index = self.read_sub_agent_index(parent_task_dir)
    index[entry["sub_task_id"]] = entry
    self._write_json_atomically(parent_task_dir / "sub_agents" / "index.json", index)
    return entry
```

Make `write_checkpoint` use `_write_json_atomically` only after retaining its
existing `json.dump`/`fsync` behavior. `read_sub_agent_index` returns `{}` for
a missing file and raises `ValueError` for malformed JSON or entries without
`sub_task_id`, so a recovery caller can fail deterministically rather than
silently invent a child.

- [ ] **Step 4: Verify the focused storage suite passes**

Run: `cd backend && uv run pytest tests/unit/application/services/test_session_file_storage.py -q`

Expected: PASS, including existing checkpoint fallback tests.

- [ ] **Step 5: Commit the storage boundary**

```bash
git add backend/src/application/services/session_file_storage.py \
  backend/tests/unit/application/services/test_session_file_storage.py
git commit -m "feat: persist sub-agent runtime metadata"
```

### Task 2: Record parent child handles and provide deterministic result application

**Files:**
- Create: `backend/src/application/services/sub_agent_recovery.py`
- Modify: `backend/src/domain/aggregates/agent/agent_state.py`
- Modify: `backend/src/application/services/agent_loop_context.py`
- Test: `backend/tests/unit/application/services/test_sub_agent_recovery.py`

**Interfaces:**
- Produces `SubAgentDispatchRecord` with `sub_task_id`, `tool_call_id`, `relative_dir`, `status`, and `updated_at`.
- Produces `record_sub_agent_dispatch(parent_state: dict, parent_task_dir: Path, runtime: dict, tool_call_id: str) -> dict`.
- Produces `apply_sub_agent_result(parent_state: dict, record: dict, result: ToolResult) -> dict`.
- Adds `pending_sub_agents: list[dict[str, Any]]` to `AgentState`, initialized to `[]`.

- [ ] **Step 1: Write failing coordinator tests**

```python
def test_record_dispatch_persists_index_and_parent_handle(tmp_path):
    coordinator = SubAgentRecoveryCoordinator(SessionFileStorage(str(tmp_path)))
    parent_dir = coordinator.storage.create_task_dir("s1", "parent-1")
    state = {"current_turn": 3, "pending_sub_agents": [], "messages": []}

    update = coordinator.record_sub_agent_dispatch(
        parent_state=state, parent_task_dir=parent_dir,
        runtime=_runtime("sub-1"), tool_call_id="call-spawn",
    )

    assert update["pending_sub_agents"] == [{
        "sub_task_id": "sub-1", "tool_call_id": "call-spawn",
        "relative_dir": "sub_agents/sub-1", "status": "running",
    }]
    assert coordinator.storage.read_sub_agent_index(parent_dir)["sub-1"]["tool_call_id"] == "call-spawn"


def test_apply_sub_agent_result_removes_original_spawn_call():
    state = {
        "messages": [], "pending_tool_calls": [{"id": "call-spawn", "name": "session_spawn"}],
        "tool_results": {}, "last_executed_tool_call_ids": [],
        "pending_sub_agents": [{"sub_task_id": "sub-1", "tool_call_id": "call-spawn"}],
    }

    update = apply_sub_agent_result(state, {"sub_task_id": "sub-1", "tool_call_id": "call-spawn"},
        ToolResult(output="child answer", success=True, metadata={"sub_task_id": "sub-1"}))

    assert update["pending_tool_calls"] == []
    assert update["pending_sub_agents"] == []
    assert update["tool_results"]["call-spawn"]["output"] == "child answer"
    assert update["messages"][0].tool_call_id == "call-spawn"
```

- [ ] **Step 2: Verify the tests fail**

Run: `cd backend && uv run pytest tests/unit/application/services/test_sub_agent_recovery.py -q`

Expected: FAIL because the coordinator and `pending_sub_agents` state do not exist.

- [ ] **Step 3: Implement one focused recovery coordinator**

Create `SubAgentRecoveryCoordinator`. It writes `runtime.json`, upserts the
`running` index entry, and returns a complete state update; it does not start
an agent or invoke a graph. `apply_sub_agent_result` creates exactly one
`ToolMessage`, updates `tool_results`, removes only the matching
`session_spawn` tool call and child handle, and sets phase to `tool_executing`.

Add `pending_sub_agents` to `AgentState` and to
`AgentLoopContext._build_initial_state`. In the runner's existing
`_configure_snapshot_storage`, add `file_storage`, `task_dir`, and a
`SubAgentRecoveryCoordinator` instance to graph config so the tool layer can
request a durable dispatch record without importing application storage
directly.

- [ ] **Step 4: Verify the coordinator suite passes**

Run: `cd backend && uv run pytest tests/unit/application/services/test_sub_agent_recovery.py -q`

Expected: PASS.

- [ ] **Step 5: Commit parent/child state primitives**

```bash
git add backend/src/application/services/sub_agent_recovery.py \
  backend/src/domain/aggregates/agent/agent_state.py \
  backend/src/application/services/agent_loop_context.py \
  backend/tests/unit/application/services/test_sub_agent_recovery.py
git commit -m "feat: track durable sub-agent handles"
```

### Task 3: Make `session_spawn` establish the durable boundary before execution

**Files:**
- Modify: `backend/src/infrastructure/tools/builtin/session_spawn.py`
- Modify: `backend/src/infrastructure/agent/nodes/tool_execute_node.py`
- Modify: `backend/src/application/services/agent_loop_runner.py`
- Test: `backend/tests/unit/infrastructure/tools/test_session_spawn.py`
- Test: `backend/tests/unit/application/services/test_agent_loop_runner_checkpoint.py`

**Interfaces:**
- `session_spawn` consumes `sub_agent_recovery_coordinator`, `file_storage`, `task_dir`, `parent_state`, and the current `tool_call_id` from `ToolContext.extra`.
- `AgentLoopRunner._save_checkpoint(...)` remains the canonical state serializer; expose it as a callback in tool context named `persist_parent_snapshot(state: dict) -> None`.
- A successful sub-agent result carries `metadata["sub_task_id"]` and `metadata["tool_call_id"]`.

- [ ] **Step 1: Write failing durable-dispatch tests**

```python
@pytest.mark.asyncio
async def test_session_spawn_persists_parent_handle_before_child_runner_starts(valid_context):
    starts: list[str] = []
    valid_context.extra["persist_parent_snapshot"] = lambda state: starts.append(
        state["pending_sub_agents"][0]["sub_task_id"]
    )
    valid_context.extra["sub_agent_recovery_coordinator"] = _coordinator_with_storage()
    valid_context.extra["file_storage"] = valid_context.extra["sub_agent_recovery_coordinator"].storage
    valid_context.extra["task_dir"] = _parent_task_dir()
    valid_context.extra["tool_call_id"] = "call-spawn"

    result = await call_session_spawn("research", valid_context)

    assert starts == [result.metadata["sub_task_id"]]
    assert valid_context.extra["sub_agent_recovery_coordinator"].storage.read_sub_agent_index(
        _parent_task_dir())[result.metadata["sub_task_id"]]["status"] == "completed"
```

```python
def test_runner_configures_parent_snapshot_callback(runner, task_dir):
    config = {"configurable": {}}
    runner._configure_snapshot_storage(config, str(task_dir))

    config["configurable"]["persist_parent_snapshot"]({
        "messages": [], "current_turn": 1, "pending_sub_agents": [],
    })

    assert runner._file_storage.read_latest_checkpoint(task_dir)["turn_number"] == 1
```

- [ ] **Step 2: Verify the tests fail**

Run: `cd backend && uv run pytest tests/unit/infrastructure/tools/test_session_spawn.py tests/unit/application/services/test_agent_loop_runner_checkpoint.py -q`

Expected: FAIL because dispatch is not persisted before the child starts and
the tool context has no parent snapshot callback.

- [ ] **Step 3: Persist, snapshot, then execute**

In `AgentLoopRunner._configure_snapshot_storage`, provide a closure named
`persist_parent_snapshot` that calls `_save_checkpoint` with the current parent
task ID and directory, and provide a `SubAgentRecoveryCoordinator`. In
`ToolExecuteNode.execute`, copy the current `state`, `file_storage`, `task_dir`,
coordinator, and callback from graph config into `ToolContext.extra`. In
`session_spawn`, do this exact ordering after creating the child Task but before
calling `runtime_use_case.execute`:

```python
runtime = make_runtime_record(
    sub_task_id=sub_task_id, parent_task_id=parent_task_id,
    session_id=parent_session_id, description=description,
    model=effective_model, workspace=context.workspace,
    max_turns=50, allowed_tools=tools,
)
record = coordinator.record_sub_agent_dispatch(
    parent_state=parent_state, parent_task_dir=Path(task_dir),
    runtime=runtime, tool_call_id=tool_call_id,
)
parent_state["pending_sub_agents"] = record["pending_sub_agents"]
persist_parent_snapshot(parent_state)
```

Then run the existing child execution and wait behavior. On child terminal
state, update the parent index before returning the `ToolResult`. Include the
child ID and original spawn call ID in result metadata. Do not mark a parent
task complete while `pending_sub_agents` is non-empty.

- [ ] **Step 4: Verify durable dispatch and existing spawn tests pass**

Run: `cd backend && uv run pytest tests/unit/infrastructure/tools/test_session_spawn.py tests/unit/application/services/test_agent_loop_runner_checkpoint.py -q`

Expected: PASS; existing synchronous success behavior remains intact.

- [ ] **Step 5: Commit the dispatch boundary**

```bash
git add backend/src/infrastructure/tools/builtin/session_spawn.py \
  backend/src/infrastructure/agent/nodes/tool_execute_node.py \
  backend/src/application/services/agent_loop_runner.py \
  backend/tests/unit/infrastructure/tools/test_session_spawn.py \
  backend/tests/unit/application/services/test_agent_loop_runner_checkpoint.py
git commit -m "feat: persist sub-agent dispatch before execution"
```

### Task 4: Restore child-mode runtime and resume parents without redispatch

**Files:**
- Modify: `backend/src/application/services/agent_loop_runner.py`
- Modify: `backend/src/application/services/agent_loop_lifecycle.py`
- Modify: `backend/src/application/services/sub_agent_recovery.py`
- Test: `backend/tests/unit/application/services/test_agent_loop_runner_checkpoint.py`
- Test: `backend/tests/unit/application/services/test_agent_loop_lifecycle.py`

**Interfaces:**
- Extends `resume_from_snapshot(*, task, task_dir, approval=None, send_message_use_case=None, sub_agent_runtime=None) -> bool`.
- Produces `resume_parent_waiting_for_children(*, parent_task, parent_task_dir, send_message_use_case) -> bool`.
- Produces `mark_sub_agent_terminal(parent_task_dir: Path, sub_task_id: str, status: str, result: str | None, error: str | None) -> dict`.

- [ ] **Step 1: Write failing recovery tests**

```python
@pytest.mark.asyncio
async def test_child_snapshot_rebuilds_sub_agent_dependencies(runner, child_runtime, child_task_dir):
    runner._file_storage.write_checkpoint(child_task_dir, _serialized_child_state(), 2)

    await runner.resume_from_snapshot(
        task=_child_task(), task_dir=child_task_dir,
        sub_agent_runtime=child_runtime,
    )

    assert runner.context_calls[-1]["is_sub_agent"] is True
    assert runner.context_calls[-1]["parent_task_id"] == "parent-1"
    assert runner.context_calls[-1]["allowed_tools"] == ["web_search"]
    assert runner.lifecycle_calls[-1]["persist_session_messages"] is False


@pytest.mark.asyncio
async def test_parent_recovery_consumes_completed_child_without_session_spawn(runner, parent_task_dir):
    _write_parent_waiting_snapshot(runner._file_storage, parent_task_dir, "sub-1", "call-spawn")
    _write_completed_child_index(runner._file_storage, parent_task_dir, "sub-1", "child answer")

    await runner.resume_from_snapshot(task=_parent_task(), task_dir=parent_task_dir)

    assert runner.graph_received_state["tool_results"]["call-spawn"]["output"] == "child answer"
    assert runner.session_spawn_calls == 0
```

- [ ] **Step 2: Verify the tests fail**

Run: `cd backend && uv run pytest tests/unit/application/services/test_agent_loop_runner_checkpoint.py tests/unit/application/services/test_agent_loop_lifecycle.py -q`

Expected: FAIL because recovery always builds a main-agent runtime and invokes
the graph with unresolved child tool calls.

- [ ] **Step 3: Rebuild the correct runtime and resolve durable children first**

At the start of `resume_from_snapshot`, deserialize state, then:

1. if `sub_agent_runtime` is supplied, call `build_all` with
   `is_sub_agent=True`, runtime parent ID, description, allowed tools, and
   `persist_session_messages=False`;
2. otherwise, if `state["pending_sub_agents"]` is non-empty, read the parent
   index before graph invocation;
3. apply each terminal child result through `apply_sub_agent_result`, save the
   parent snapshot, and invoke a fresh parent graph only once no children
   remain;
4. for a nonterminal child, recover that existing child by its runtime and
   snapshot. If its task has no usable child snapshot, fail the parent with a
   recovery error instead of dispatching a replacement.

When a child reaches normal completion, failure, or cancellation, call
`mark_sub_agent_terminal` before final lifecycle handling. If a recovered
parent has just become unblocked, schedule exactly one
`resume_from_snapshot(parent_task, parent_task_dir)` through a per-parent
`asyncio.Lock` in `SubAgentRecoveryCoordinator`; late callbacks must skip a
cancelled or terminal parent.

- [ ] **Step 4: Verify child and parent recovery tests pass**

Run: `cd backend && uv run pytest tests/unit/application/services/test_agent_loop_runner_checkpoint.py tests/unit/application/services/test_agent_loop_lifecycle.py -q`

Expected: PASS; the graph sees the completed child `ToolMessage`, and no
replacement child is created.

- [ ] **Step 5: Commit recovery coordination**

```bash
git add backend/src/application/services/agent_loop_runner.py \
  backend/src/application/services/agent_loop_lifecycle.py \
  backend/src/application/services/sub_agent_recovery.py \
  backend/tests/unit/application/services/test_agent_loop_runner_checkpoint.py \
  backend/tests/unit/application/services/test_agent_loop_lifecycle.py
git commit -m "feat: resume durable sub-agent tasks"
```

### Task 5: Route parent approvals to the actual awaiting child

**Files:**
- Modify: `backend/src/presentation/routes/tasks.py`
- Modify: `backend/src/infrastructure/tools/builtin/session_spawn.py`
- Test: `backend/tests/unit/presentation/test_approvals_route.py`

**Interfaces:**
- `submit_approval(parent_task_id, dto, ...)` consumes parent `index.json` and locates a child by `tool_call_id`.
- Child approval calls `resume_from_snapshot(task=child_task, task_dir=child_dir, approval=..., sub_agent_runtime=runtime)`.
- Parent-task approval returns the existing response JSON shape, with `task_id` remaining the parent ID.

- [ ] **Step 1: Write failing approval-route tests**

```python
@pytest.mark.asyncio
async def test_parent_approval_resumes_awaiting_child_snapshot(monkeypatch, route_dependencies):
    parent_dir, child_dir = _seed_parent_with_awaiting_child(
        tool_call_id="call-dangerous", sub_task_id="sub-1")
    resumed: list[dict] = []
    route_dependencies.loop_runner.resume_from_snapshot = AsyncMock(
        side_effect=lambda **kwargs: resumed.append(kwargs))

    response = await submit_approval(
        "parent-1", ApprovalDecisionDTO(toolCallId="call-dangerous", decision="allow_once"),
        route_dependencies.registry, route_dependencies.request,
    )

    assert response["task_id"] == "parent-1"
    assert resumed[0]["task"].id == "sub-1"
    assert resumed[0]["task_dir"] == child_dir
    assert resumed[0]["sub_agent_runtime"]["parent_task_id"] == "parent-1"


@pytest.mark.asyncio
async def test_parent_approval_rejects_index_entry_with_mismatched_child_snapshot(route_dependencies):
    _seed_parent_index_with_wrong_tool_call()

    with pytest.raises(HTTPException, match="NO_PENDING_APPROVAL"):
        await submit_approval("parent-1", ApprovalDecisionDTO(toolCallId="call-1", decision="deny"),
            route_dependencies.registry, route_dependencies.request)
```

- [ ] **Step 2: Verify the tests fail**

Run: `cd backend && uv run pytest tests/unit/presentation/test_approvals_route.py -q`

Expected: FAIL because the route reads only `<parent>/checkpoints`.

- [ ] **Step 3: Resolve the child safely while retaining the parent API**

Keep the existing parent snapshot lookup first. If it has no matching pending
confirmation, read the parent child index, find an awaiting entry for the DTO
tool call, read its `runtime.json`, fetch its Task from the repository, and
validate the actual child snapshot's pending tool call. Only then remove the
in-memory registry entry and schedule child `resume_from_snapshot`. A missing
runtime document, child task, index entry, or mismatched snapshot returns the
current 404 `NO_PENDING_APPROVAL` response; none may fall back to dispatching
a child.

- [ ] **Step 4: Verify route and confirmation regression tests pass**

Run: `cd backend && uv run pytest tests/unit/presentation/test_approvals_route.py tests/unit/infrastructure/agent/test_protocol_nodes.py -q`

Expected: PASS; main-agent approvals still work and child approval selects the
actual child exactly once.

- [ ] **Step 5: Commit parent-scoped approval routing**

```bash
git add backend/src/presentation/routes/tasks.py \
  backend/src/infrastructure/tools/builtin/session_spawn.py \
  backend/tests/unit/presentation/test_approvals_route.py
git commit -m "feat: resume sub-agent approvals from parent tasks"
```

### Task 6: Document the task tree and run end-to-end verification

**Files:**
- Modify: `README.md`
- Modify: `docs/langgraph-workflow.md`
- Modify: `docs/superpowers/specs/2026-08-31-local-agent-state-recovery-design.md`
- Test: `backend/tests/integration/test_sub_agent_recovery.py`

**Interfaces:**
- Documents `sub_agents/index.json`, child `runtime.json`, and the parent-scoped approval contract.
- Integration test simulates fresh runner instances to represent a process restart.

- [ ] **Step 1: Write a failing fresh-runtime integration test**

```python
@pytest.mark.asyncio
async def test_restart_recovers_existing_child_and_parent_without_duplicate_dispatch(app_runtime):
    parent_id, child_id = await app_runtime.dispatch_child_and_persist_parent()
    await app_runtime.stop_process_before_child_returns()

    restarted = await app_runtime.create_fresh_runtime()
    await restarted.complete_child(child_id, output="child answer")
    await restarted.resume_parent(parent_id)

    assert restarted.spawn_count(child_id) == 1
    assert restarted.parent_result(parent_id).tool_results["call-spawn"]["output"] == "child answer"
```

- [ ] **Step 2: Verify the integration test fails before final wiring**

Run: `cd backend && uv run pytest tests/integration/test_sub_agent_recovery.py -q`

Expected: FAIL until the parent/child lifecycle wiring is complete.

- [ ] **Step 3: Add only the required documentation and test fixtures**

Document that LangGraph remains an execution engine only, while the durable
parent child index and child snapshots drive restart recovery. State clearly
that parent approvals can target a child but retain the parent task ID. Explain
that an in-flight child action after its latest snapshot may be retried, while
an already-recorded child handle is never re-dispatched.

- [ ] **Step 4: Run focused, full, lint, and local API verification**

Run:

```bash
cd backend
uv run pytest tests/unit/application/services/test_session_file_storage.py \
  tests/unit/application/services/test_sub_agent_recovery.py \
  tests/unit/application/services/test_agent_loop_runner_checkpoint.py \
  tests/unit/infrastructure/tools/test_session_spawn.py \
  tests/unit/presentation/test_approvals_route.py \
  tests/integration/test_sub_agent_recovery.py -q
uv run pytest -q
uv run ruff check src/application/services/session_file_storage.py \
  src/application/services/sub_agent_recovery.py \
  src/application/services/agent_loop_context.py \
  src/application/services/agent_loop_runner.py \
  src/infrastructure/tools/builtin/session_spawn.py \
  src/infrastructure/agent/nodes/tool_execute_node.py \
  src/presentation/routes/tasks.py \
  tests/unit/application/services/test_session_file_storage.py \
  tests/unit/application/services/test_sub_agent_recovery.py \
  tests/unit/application/services/test_agent_loop_runner_checkpoint.py \
  tests/unit/application/services/test_agent_loop_lifecycle.py \
  tests/unit/infrastructure/tools/test_session_spawn.py \
  tests/unit/presentation/test_approvals_route.py \
  tests/integration/test_sub_agent_recovery.py
uv run uvicorn src.presentation.app:app --host 127.0.0.1 --port 8000
```

While Uvicorn is running, verify:

```bash
curl -fsS http://127.0.0.1:8000/health | jq -e '.status == "ok"'
curl -fsS http://127.0.0.1:8000/openapi.json | jq -e \
  '.paths["/api/tasks/{task_id}/approvals"].post.description | contains("本地状态快照")'
```

Expected: all focused and full tests pass, Ruff passes for every modified file,
and the backend health endpoint returns 200. Stop Uvicorn after the smoke test.

- [ ] **Step 5: Commit documentation and final tests**

```bash
git add README.md docs/langgraph-workflow.md \
  docs/superpowers/specs/2026-08-31-local-agent-state-recovery-design.md \
  backend/tests/integration/test_sub_agent_recovery.py
git commit -m "docs: describe durable sub-agent recovery"
```
