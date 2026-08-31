"""Tests for AgentLoopRunner checkpoint save behavior."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.application.services.session_file_storage import SessionFileStorage
from src.application.services.agent_loop_runner import AgentLoopRunner


class FakeAgentRepo:
    pass


class FakeLLMProvider:
    pass


class FakePromptContext:
    pass


class FakeMessageRepo:
    pass


class FakeSkillRepo:
    pass


class FakeTaskRepo:
    pass


class FakeSessionRepo:
    pass


class FakeEventEmitter:
    pass


class FakeToolRegistry:
    pass


class FakeWorkflowBuilder:
    pass


class FakeTaskCompletionService:
    pass


def make_minimal_runner(file_storage=None):
    """Build a minimal AgentLoopRunner for testing _save_checkpoint."""
    return AgentLoopRunner(
        agent_repo=FakeAgentRepo(),
        llm_provider=FakeLLMProvider(),
        prompt_context=FakePromptContext(),
        message_repo=FakeMessageRepo(),
        skill_repo=FakeSkillRepo(),
        task_repo=FakeTaskRepo(),
        session_repo=FakeSessionRepo(),
        event_emitter=FakeEventEmitter(),
        tool_registry=FakeToolRegistry(),
        workflow_builder=FakeWorkflowBuilder(),
        task_completion_service=FakeTaskCompletionService(),
        file_storage=file_storage,
    )


class TestSaveCheckpoint:
    """Tests for _save_checkpoint method."""

    def test_saves_checkpoint_to_file_storage(self, tmp_path):
        storage = SessionFileStorage(base_path=str(tmp_path))
        task_dir = storage.create_task_dir("sess-001", "task-001")

        runner = make_minimal_runner(file_storage=storage)

        state = {
            "messages": [HumanMessage(content="Hello"), AIMessage(content="Hi!")],
            "task_id": "task-001",
            "current_turn": 3,
            "workspace": "/tmp/ws",
            "user_message": "Hello",
            "task_start_message_count": 2,
            "model": "gpt-4",
            "max_turns": 10,
            "phase": "executing",
            "should_end": False,
            "is_complete": False,
            "pending_tool_calls": [],
            "tool_results": {},
            "awaiting_user_input": False,
            "last_executed_tool_call_ids": [],
            "current_llm_text": "",
            "system_prompt": "",
            "thinking_text": "",
            "final_result": None,
            "error": None,
            "max_context_tokens": 128000,
            "context_token_estimate": 100,
            "context_token_baseline": None,
            "context_token_baseline_message_count": 0,
            "context_compaction_attempts": 0,
            "emergency_compact_requested": False,
            "last_context_strategy": None,
            "is_sub_agent": False,
            "parent_task_id": None,
        }

        runner._save_checkpoint("task-001", str(task_dir), state)

        checkpoint = storage.read_latest_checkpoint(task_dir)
        assert checkpoint is not None
        assert checkpoint["turn_number"] == 3
        assert checkpoint["state"]["current_turn"] == 3
        assert checkpoint["state"]["task_id"] == "task-001"
        assert checkpoint["state"]["phase"] == "executing"

    def test_noop_when_file_storage_is_none(self, tmp_path):
        storage = SessionFileStorage(base_path=str(tmp_path))
        task_dir = storage.create_task_dir("sess-001", "task-001")

        runner = make_minimal_runner(file_storage=None)

        state = {"current_turn": 1}
        # Should not raise
        runner._save_checkpoint("task-001", str(task_dir), state)

        checkpoint = storage.read_latest_checkpoint(task_dir)
        assert checkpoint is None

    def test_noop_when_task_dir_is_none(self, tmp_path):
        storage = SessionFileStorage(base_path=str(tmp_path))
        runner = make_minimal_runner(file_storage=storage)

        # Should not raise
        runner._save_checkpoint("task-001", None, {"current_turn": 1})

    def test_handles_non_serializable_state_gracefully(self, tmp_path):
        """Should log error but not crash when save fails."""
        storage = SessionFileStorage(base_path=str(tmp_path))
        task_dir = storage.create_task_dir("sess-001", "task-001")
        runner = make_minimal_runner(file_storage=storage)

        # A state with a non-serializable message that message_to_dict can't handle
        runner._save_checkpoint("task-001", str(task_dir), {"current_turn": 1, "messages": []})

        checkpoint = storage.read_latest_checkpoint(task_dir)
        assert checkpoint is not None
        assert checkpoint["turn_number"] == 1


def test_runner_adds_local_storage_to_graph_config(tmp_path):
    storage = SessionFileStorage(base_path=str(tmp_path))
    task_dir = storage.create_task_dir("sess-001", "task-001")
    runner = make_minimal_runner(file_storage=storage)
    graph_config = {"configurable": {}}

    runner._configure_snapshot_storage(graph_config, str(task_dir))

    assert graph_config["configurable"]["file_storage"] is storage
    assert graph_config["configurable"]["task_dir"] == str(task_dir)


@pytest.mark.asyncio
async def test_runner_resumes_pending_tool_from_local_snapshot(tmp_path):
    storage = SessionFileStorage(base_path=str(tmp_path))
    task_dir = storage.create_task_dir("sess-001", "task-001")
    state = {
        "messages": [],
        "current_turn": 2,
        "pending_tool_calls": [{"id": "call-1", "name": "shell", "input": {}}],
        "tool_results": {},
        "pending_confirmation": {"tool_call_id": "call-1"},
        "workspace": "/tmp/ws",
        "task_id": "task-001",
    }
    storage.write_checkpoint(
        task_dir,
        state,
        2,
        resume_status="awaiting_confirmation",
        pending_confirmation=state["pending_confirmation"],
    )
    runner = make_minimal_runner(file_storage=storage)

    class FakeToolRegistry:
        async def execute(self, tool_name, tool_input, context):
            if not context.extra.get("bypass_confirmation"):
                return SimpleNamespace(
                    output=None,
                    success=False,
                    error="confirmation_required",
                    metadata={
                        "confirmation_required": True,
                        "tool_call_id": "call-1",
                        "command": "rm -rf build",
                        "category": "destructive",
                        "risk_reason": "destructive operation",
                    },
                )
            return SimpleNamespace(output="executed", success=True, error=None, metadata={})

    class FakeGraph:
        async def ainvoke(self, restored_state, graph_config):
            assert restored_state["tool_results"]["call-1"]["output"] == "executed"
            return {**restored_state, "final_result": "done", "pending_confirmation": None}

    graph_config = {
        "configurable": {
            "tool_registry": FakeToolRegistry(),
            "event_emitter": AsyncMock(),
            "agent_id": "agent-1",
            "session_id": "sess-001",
        }
    }
    runner._context.build_all = AsyncMock(return_value=(FakeGraph(), graph_config, {}))
    runner._lifecycle.handle_normal_completion = AsyncMock()
    task = SimpleNamespace(
        id="task-001", agent_id="agent-1", session_id="sess-001",
        message="continue", model="test", max_turns=5, workspace="/tmp/ws",
    )

    resumed = await runner.resume_from_snapshot(
        task=task,
        task_dir=task_dir,
        approval={"tool_call_id": "call-1", "decision": "allow_once"},
    )

    assert resumed is True
    runner._lifecycle.handle_normal_completion.assert_awaited_once()
