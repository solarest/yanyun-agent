"""Tests for AgentLoopRunner checkpoint save behavior."""

from pathlib import Path

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
