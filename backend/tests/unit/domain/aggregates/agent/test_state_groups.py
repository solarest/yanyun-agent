"""Tests for AgentState grouped accessors (state_groups.py)

Covers state-accessors spec requirements:
- ControlFields, ContextFields, ToolFields, TaskFields
- from_state() reading with defaults
- to_update() writing
- Key mapping between dataclass fields and AgentState dict keys
"""

import pytest
from src.domain.aggregates.agent.state_groups import (
    ControlFields,
    ContextFields,
    ToolFields,
    TaskFields,
)


# ─────────────────────────────────────────────────────────────────
# ControlFields
# ─────────────────────────────────────────────────────────────────

class TestControlFields:
    """Spec: Reading control flow fields via ControlFields"""

    def test_from_state_reads_all_fields_with_values(self):
        """from_state() populates all fields from a fully-specified state dict"""
        state = {
            "current_turn": 5,
            "max_turns": 50,
            "phase": "thinking",
            "should_end": True,
            "is_complete": False,
        }
        cf = ControlFields.from_state(state)
        assert cf.current_turn == 5
        assert cf.max_turns == 50
        assert cf.phase == "thinking"
        assert cf.should_end is True
        assert cf.is_complete is False

    def test_from_state_uses_defaults_for_empty_state(self):
        """from_state() returns defaults when state is empty"""
        cf = ControlFields.from_state({})
        assert cf.current_turn == 0
        assert cf.max_turns == 100
        assert cf.phase == "idle"
        assert cf.should_end is False
        assert cf.is_complete is False

    def test_to_update_produces_correct_dict(self):
        """Spec: Writing state updates via ControlFields.to_update"""
        cf = ControlFields(
            current_turn=3,
            max_turns=100,
            phase="executing",
            should_end=False,
            is_complete=True,
        )
        update = cf.to_update()
        assert update == {
            "current_turn": 3,
            "max_turns": 100,
            "phase": "executing",
            "should_end": False,
            "is_complete": True,
        }

    def test_roundtrip_from_state_to_update(self):
        """from_state() then to_update() produces the original state (minus unknown keys)"""
        original = {
            "current_turn": 7,
            "max_turns": 200,
            "phase": "tool_executing",
            "should_end": False,
            "is_complete": False,
            "extra_field": "should_be_ignored",
        }
        cf = ControlFields.from_state(original)
        result = cf.to_update()
        assert result["current_turn"] == 7
        assert result["max_turns"] == 200
        assert result["phase"] == "tool_executing"
        assert "extra_field" not in result


# ─────────────────────────────────────────────────────────────────
# ContextFields
# ─────────────────────────────────────────────────────────────────

class TestContextFields:
    """Spec: ContextFields for context management fields"""

    def test_from_state_reads_all_fields(self):
        """from_state() maps AgentState keys to ContextFields attributes"""
        state = {
            "max_context_tokens": 64_000,
            "context_token_estimate": 12_000,
            "context_token_baseline": 10_000,
            "context_token_baseline_message_count": 15,
            "context_compaction_attempts": 2,
            "emergency_compact_requested": True,
            "last_context_strategy": "micro_compact",
        }
        ctx = ContextFields.from_state(state)
        assert ctx.max_tokens == 64_000
        assert ctx.estimate == 12_000
        assert ctx.baseline == 10_000
        assert ctx.baseline_count == 15
        assert ctx.compaction_attempts == 2
        assert ctx.emergency_requested is True
        assert ctx.last_strategy == "micro_compact"

    def test_from_state_defaults(self):
        """from_state() provides sensible defaults for empty state"""
        ctx = ContextFields.from_state({})
        assert ctx.max_tokens == 128_000
        assert ctx.estimate == 0
        assert ctx.baseline is None
        assert ctx.baseline_count == 0
        assert ctx.compaction_attempts == 0
        assert ctx.emergency_requested is False
        assert ctx.last_strategy is None

    def test_to_update_maps_back_to_agent_state_keys(self):
        """to_update() converts dataclass fields back to AgentState dict keys"""
        ctx = ContextFields(
            max_tokens=32_000,
            estimate=5_000,
            baseline=4_500,
            baseline_count=10,
            compaction_attempts=1,
            emergency_requested=False,
            last_strategy="soft_prune",
        )
        update = ctx.to_update()
        assert update == {
            "max_context_tokens": 32_000,
            "context_token_estimate": 5_000,
            "context_token_baseline": 4_500,
            "context_token_baseline_message_count": 10,
            "context_compaction_attempts": 1,
            "emergency_compact_requested": False,
            "last_context_strategy": "soft_prune",
        }

    def test_baseline_none_preserved(self):
        """to_update() preserves None baseline (important for invalidation)"""
        ctx = ContextFields(baseline=None, last_strategy=None)
        update = ctx.to_update()
        assert update["context_token_baseline"] is None
        assert update["last_context_strategy"] is None


# ─────────────────────────────────────────────────────────────────
# ToolFields
# ─────────────────────────────────────────────────────────────────

class TestToolFields:
    """Spec: ToolFields for tool execution state"""

    def test_from_state_reads_pending_and_results(self):
        """from_state() reads tool-related state fields"""
        state = {
            "pending_tool_calls": [{"id": "1", "name": "read"}],
            "tool_results": {"1": {"output": "content"}},
            "awaiting_user_input": True,
            "last_executed_tool_call_ids": ["1"],
            "final_result": "done",
        }
        tf = ToolFields.from_state(state)
        assert tf.pending == [{"id": "1", "name": "read"}]
        assert tf.results == {"1": {"output": "content"}}
        assert tf.awaiting_input is True
        assert tf.last_executed_ids == ["1"]
        assert tf.final_result == "done"

    def test_from_state_defaults_for_empty_state(self):
        """from_state() provides empty defaults for empty state"""
        tf = ToolFields.from_state({})
        assert tf.pending == []
        assert tf.results == {}
        assert tf.awaiting_input is False
        assert tf.last_executed_ids == []
        assert tf.final_result is None

    def test_to_update_writes_results_and_clears_pending(self):
        """Spec: to_update() includes pending_tool_calls (cleared) and tool_results"""
        tf = ToolFields(
            pending=[],
            results={"1": {"output": "test"}},
            awaiting_input=False,
            last_executed_ids=["1"],
            final_result=None,
        )
        update = tf.to_update()
        assert update == {
            "pending_tool_calls": [],
            "tool_results": {"1": {"output": "test"}},
            "awaiting_user_input": False,
            "last_executed_tool_call_ids": ["1"],
            "final_result": None,
        }


# ─────────────────────────────────────────────────────────────────
# TaskFields
# ─────────────────────────────────────────────────────────────────

class TestTaskFields:
    """Spec: TaskFields for immutable task context"""

    def test_from_state_reads_task_identification_fields(self):
        """from_state() reads task identity fields"""
        state = {
            "task_id": "task-123",
            "workspace": "/tmp/ws",
            "user_message": "build feature X",
            "task_start_message_count": 3,
            "model": "opus",
            "system_prompt": "You are a helpful assistant.",
            "is_sub_agent": True,
            "parent_task_id": "task-parent",
        }
        tf = TaskFields.from_state(state)
        assert tf.task_id == "task-123"
        assert tf.workspace == "/tmp/ws"
        assert tf.user_message == "build feature X"
        assert tf.task_start_message_count == 3
        assert tf.model == "opus"
        assert tf.system_prompt == "You are a helpful assistant."
        assert tf.is_sub_agent is True
        assert tf.parent_task_id == "task-parent"

    def test_from_state_defaults(self):
        """from_state() provides empty defaults"""
        tf = TaskFields.from_state({})
        assert tf.task_id == ""
        assert tf.workspace == ""
        assert tf.user_message == ""
        assert tf.model == ""
        assert tf.system_prompt == ""
        assert tf.is_sub_agent is False
        assert tf.parent_task_id is None

    def test_to_update_for_initial_state_construction(self):
        """Spec: TaskFields used in initial state construction"""
        tf = TaskFields(
            task_id="task-456",
            workspace="/ws",
            user_message="hello",
            task_start_message_count=1,
            model="sonnet",
            system_prompt="You are helpful.",
            is_sub_agent=False,
            parent_task_id=None,
        )
        update = tf.to_update()
        assert update["task_id"] == "task-456"
        assert update["workspace"] == "/ws"
        assert update["is_sub_agent"] is False
        assert update["parent_task_id"] is None
