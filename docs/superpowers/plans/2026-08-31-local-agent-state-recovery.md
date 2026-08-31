# Local Agent State Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace LangGraph checkpoint recovery with recoverable task-local AgentState files.

**Architecture:** SessionFileStorage writes atomic JSON AgentState snapshots. LangGraph remains the executor but is compiled without a checkpointer; a persistence node dumps merged state after each tool and the runner restores a snapshot into a fresh runtime.

**Tech Stack:** Python 3.12, FastAPI, LangGraph StateGraph, LangChain, pytest.

**Spec:** `docs/superpowers/specs/2026-08-31-local-agent-state-recovery-design.md`

## Global Constraints

- Never serialize, load, or use `MemorySaver`, `Command(resume=...)`, or an in-memory graph-resume registry.
- Persist only task-local state, after each completed tool and at every terminal boundary.
- Preserve the existing SSE event schema and `POST /api/tasks/{task_id}/approvals` request contract.
- A corrupt newest snapshot must fall back to the newest readable prior snapshot.
- Every production behavior starts with an observed failing test.

---

### Task 1: Persist atomic, recoverable AgentState

**Files:**
- Modify: `backend/src/application/services/session_file_storage.py`
- Modify: `backend/src/domain/aggregates/agent/agent_state.py`
- Test: `backend/tests/unit/application/services/test_session_file_storage.py`
- Test: `backend/tests/unit/domain/services/test_checkpoint_serializer.py`

**Interfaces:**
- Produces `write_checkpoint(task_dir, state, turn_number, *, resume_status="running", pending_confirmation=None) -> Path`.
- Produces a checkpoint document with `turn_number`, `saved_at`, `resume_status`, `pending_confirmation`, and serialized `state`.
- Adds `pending_confirmation: dict | None` to AgentState.

- [ ] **Step 1: Write failing tests**

```python
def test_read_latest_checkpoint_skips_corrupt_newer_snapshot(tmp_path):
    storage = SessionFileStorage(base_path=str(tmp_path))
    task_dir = storage.create_task_dir("session-1", "task-1")
    storage.write_checkpoint(task_dir, {"messages": []}, 1)
    (task_dir / "checkpoints" / "turn_002.json").write_text("{")
    assert storage.read_latest_checkpoint(task_dir)["turn_number"] == 1

def test_checkpoint_records_pending_confirmation(tmp_path):
    storage = SessionFileStorage(base_path=str(tmp_path))
    task_dir = storage.create_task_dir("session-1", "task-1")
    storage.write_checkpoint(task_dir, {"messages": []}, 2,
        resume_status="awaiting_confirmation",
        pending_confirmation={"tool_call_id": "call-1", "tool_name": "shell"})
    assert storage.read_latest_checkpoint(task_dir)["pending_confirmation"]["tool_call_id"] == "call-1"
```

- [ ] **Step 2: Verify RED**

Run: `cd backend && uv run pytest tests/unit/application/services/test_session_file_storage.py tests/unit/domain/services/test_checkpoint_serializer.py -q`

Expected: FAIL because recovery metadata and corrupt-file fallback do not exist.

- [ ] **Step 3: Implement the smallest atomic format**

```python
payload = {"turn_number": turn_number, "saved_at": datetime.now(UTC).isoformat(),
           "resume_status": resume_status, "pending_confirmation": pending_confirmation,
           "state": state}
temporary = target.with_suffix(".json.tmp")
temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
temporary.replace(target)
```

Read descending checkpoint files, return the first JSON document that parses, and retain the existing message serializer.

- [ ] **Step 4: Verify GREEN**

Run: `cd backend && uv run pytest tests/unit/application/services/test_session_file_storage.py tests/unit/domain/services/test_checkpoint_serializer.py -q`

Expected: PASS.

### Task 2: Dump state after tools without a LangGraph checkpointer

**Files:**
- Create: `backend/src/infrastructure/agent/persist_state_node.py`
- Modify: `backend/src/infrastructure/agent/workflow_builder.py`
- Modify: `backend/src/application/services/agent_loop_context.py`
- Modify: `backend/src/application/services/agent_loop_runner.py`
- Modify: `backend/src/application/agent_loop/send_message.py`
- Test: `backend/tests/unit/infrastructure/agent/test_persist_state_node.py`
- Test: `backend/tests/unit/application/services/test_agent_loop_runner_checkpoint.py`

**Interfaces:**
- Produces `async persist_state_node(state, config) -> dict`.
- Consumes `config["configurable"]["file_storage"]` and `config["configurable"]["task_dir"]`.
- Produces `AgentLoopRunner.resume_from_snapshot(task, task_dir, *, approval=None) -> None`.

- [ ] **Step 1: Write failing tests**

```python
@pytest.mark.asyncio
async def test_persist_state_node_writes_merged_tool_result(tmp_path):
    storage = SessionFileStorage(base_path=str(tmp_path))
    task_dir = storage.create_task_dir("session-1", "task-1")
    state = {"messages": [], "current_turn": 2,
             "tool_results": {"call-1": {"output": "done"}}}
    await persist_state_node(state, {"configurable": {
        "file_storage": storage, "task_dir": str(task_dir)}})
    assert storage.read_latest_checkpoint(task_dir)["state"]["tool_results"]["call-1"]["output"] == "done"

def test_workflow_does_not_install_a_checkpointer():
    assert AgentWorkflowBuilder.build().checkpointer is None
```

- [ ] **Step 2: Verify RED**

Run: `cd backend && uv run pytest tests/unit/infrastructure/agent/test_persist_state_node.py tests/unit/application/services/test_agent_loop_runner_checkpoint.py -q`

Expected: FAIL because the node is absent and the compiled graph installs MemorySaver.

- [ ] **Step 3: Implement the persistence boundary**

```python
async def persist_state_node(state, config):
    cfg = config.get("configurable", {})
    if cfg.get("file_storage") and cfg.get("task_dir"):
        cfg["file_storage"].write_checkpoint(
            Path(cfg["task_dir"]), serialize_agent_state(state),
            state.get("current_turn", 0))
    return {}
```

Compile the graph without `MemorySaver`; send every `tool_execute` transition through `persist_state` before `route_after_tool_execute`. Pass storage and task directory through graph config. Delete `resume_meta.json`, `checkpointer_file`, and runner methods that write or load checkpointer internals.

- [ ] **Step 4: Verify GREEN**

Run: `cd backend && uv run pytest tests/unit/infrastructure/agent/test_persist_state_node.py tests/unit/application/services/test_agent_loop_runner_checkpoint.py -q`

Expected: PASS.

### Task 3: Persist and resume confirmations as application data

**Files:**
- Modify: `backend/src/infrastructure/agent/nodes/tool_execute_node.py`
- Modify: `backend/src/domain/agent_loop/agent_routing.py`
- Modify: `backend/src/application/services/agent_loop_lifecycle.py`
- Modify: `backend/src/presentation/routes/tasks.py`
- Modify: `backend/src/presentation/dependencies.py`
- Delete: `backend/src/infrastructure/agent/file_backed_saver.py`
- Delete: `backend/src/infrastructure/agent/save_checkpoint_node.py`
- Delete: `backend/src/infrastructure/agent/graph_resume_manager.py`
- Test: `backend/tests/unit/infrastructure/agent/test_protocol_nodes.py`
- Test: `backend/tests/unit/presentation/test_approvals_route.py`
- Delete: the unit tests dedicated to the three deleted recovery modules.

**Interfaces:**
- Consumes an optional config approval: `{"tool_call_id": str, "decision": "allow_once" | "allow_all" | "deny"}`.
- Produces `pending_confirmation` while retaining the pending tool call until the approval is applied.

- [ ] **Step 1: Write failing tests**

```python
@pytest.mark.asyncio
async def test_confirmation_returns_persistable_state_without_graph_interrupt():
    result = await tool_execute_node(state_with_dangerous_shell(), confirmation_config())
    assert result["pending_confirmation"]["tool_call_id"] == "call-dangerous"
    assert result["pending_tool_calls"][0]["id"] == "call-dangerous"
```

Add an approval-route test that seeds a local `awaiting_confirmation` snapshot, accepts `allow_once`, and verifies the recorded tool executes once.

- [ ] **Step 2: Verify RED**

Run: `cd backend && uv run pytest tests/unit/infrastructure/agent/test_protocol_nodes.py tests/unit/presentation/test_approvals_route.py -q`

Expected: FAIL because the tool node calls `interrupt()` and the route imports GraphResumeManager.

- [ ] **Step 3: Implement local continuation**

```python
if confirmation_required and approval is None:
    return {"pending_tool_calls": pending_tools,
            "pending_confirmation": confirmation_record,
            "phase": "awaiting_confirmation"}
if approval and approval["decision"] == "deny":
    result_dict = denied_tool_result(tc)
else:
    result_dict = await execute_with_confirmation_bypass(tc, tool_context)
```

Route a state with `pending_confirmation` to END. The lifecycle keeps its task RUNNING without finalization. The approval route loads and validates the latest snapshot, delegates to `resume_from_snapshot`, and returns the existing success payload. That runner applies the decision, saves the resulting state, then invokes a fresh graph from the updated state. Remove GraphInterrupt, Command, and graph-resume imports and files.

- [ ] **Step 4: Verify GREEN**

Run: `cd backend && uv run pytest tests/unit/infrastructure/agent/test_protocol_nodes.py tests/unit/presentation/test_approvals_route.py -q`

Expected: PASS; allow and deny resume without LangGraph recovery.

### Task 4: Verify restart recovery and update documentation

**Files:**
- Modify: `README.md`
- Modify: `docs/langgraph-workflow.md`
- Test: `backend/tests/unit/application/services/test_agent_loop_runner_checkpoint.py`

**Interfaces:**
- Consumes a readable snapshot with serialized AgentState.
- Produces a fresh graph invocation using deserialized state and no checkpointer.

- [ ] **Step 1: Write the failing restart test**

```python
@pytest.mark.asyncio
async def test_runner_resumes_latest_local_state_without_checkpointer(tmp_path, runner):
    task_dir = prepare_running_snapshot(tmp_path, turn=2)
    await runner.resume_from_snapshot(task, task_dir)
    assert runner.graph_received_state["current_turn"] == 2
```

- [ ] **Step 2: Verify RED**

Run: `cd backend && uv run pytest tests/unit/application/services/test_agent_loop_runner_checkpoint.py -q`

Expected: FAIL until the runner calls `read_latest_checkpoint()` and `deserialize_agent_state()`.

- [ ] **Step 3: Finish the restart path and documentation**

Document: “LangGraph executes the state machine; unfinished-task recovery reads `checkpoints/turn_N.json` and never restores a LangGraph checkpointer.” Do not alter SSE event names or approval request/response DTOs.

- [ ] **Step 4: Run focused and full verification**

Run: `cd backend && uv run pytest tests/unit/application/services/test_session_file_storage.py tests/unit/application/services/test_agent_loop_runner_checkpoint.py tests/unit/infrastructure/agent/test_protocol_nodes.py tests/unit/presentation/test_approvals_route.py -q && uv run pytest -q && uv run ruff check src tests`

Expected: all tests and Ruff checks pass.
