"""Tests for file-backed AgentState persistence at graph boundaries."""

import pytest

from src.application.services.session_file_storage import SessionFileStorage
from src.infrastructure.agent.workflow_builder import AgentWorkflowBuilder


@pytest.mark.asyncio
async def test_persist_state_node_writes_merged_tool_result(tmp_path):
    from src.infrastructure.agent.persist_state_node import persist_state_node

    storage = SessionFileStorage(base_path=str(tmp_path))
    task_dir = storage.create_task_dir("session-1", "task-1")
    state = {
        "messages": [],
        "current_turn": 2,
        "tool_results": {"call-1": {"output": "done"}},
    }

    result = await persist_state_node(
        state,
        {"configurable": {"file_storage": storage, "task_dir": str(task_dir)}},
    )

    checkpoint = storage.read_latest_checkpoint(task_dir)
    assert result == {}
    assert checkpoint["state"]["tool_results"]["call-1"]["output"] == "done"


@pytest.mark.asyncio
async def test_persist_state_node_marks_pending_confirmation(tmp_path):
    from src.infrastructure.agent.persist_state_node import persist_state_node

    storage = SessionFileStorage(base_path=str(tmp_path))
    task_dir = storage.create_task_dir("session-1", "task-1")

    await persist_state_node(
        {
            "messages": [],
            "current_turn": 2,
            "pending_confirmation": {"tool_call_id": "call-dangerous"},
        },
        {"configurable": {"file_storage": storage, "task_dir": str(task_dir)}},
    )

    checkpoint = storage.read_latest_checkpoint(task_dir)
    assert checkpoint["resume_status"] == "awaiting_confirmation"
    assert checkpoint["pending_confirmation"]["tool_call_id"] == "call-dangerous"


def test_workflow_does_not_install_a_checkpointer():
    AgentWorkflowBuilder.reset()

    graph = AgentWorkflowBuilder.build()

    assert graph.checkpointer is None
