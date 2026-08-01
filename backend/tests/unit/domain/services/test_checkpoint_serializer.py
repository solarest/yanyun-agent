"""Tests for AgentState checkpoint serialization."""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src.domain.services.checkpoint_serializer import (
    deserialize_agent_state,
    serialize_agent_state,
)


def make_sample_state(**overrides):
    """Build a minimal AgentState dict for testing."""
    state = {
        "messages": [
            SystemMessage(content="You are helpful."),
            HumanMessage(content="Hello"),
            AIMessage(content="Hi there!", tool_calls=[]),
        ],
        "task_id": "task-001",
        "workspace": "/tmp/ws",
        "user_message": "Hello",
        "task_start_message_count": 3,
        "model": "gpt-4",
        "current_turn": 2,
        "max_turns": 10,
        "phase": "executing",
        "should_end": False,
        "is_complete": False,
        "pending_tool_calls": [],
        "tool_results": {},
        "awaiting_user_input": False,
        "last_executed_tool_call_ids": [],
        "current_llm_text": "",
        "system_prompt": "You are helpful.",
        "thinking_text": "",
        "final_result": None,
        "error": None,
        "max_context_tokens": 128000,
        "context_token_estimate": 500,
        "context_token_baseline": None,
        "context_token_baseline_message_count": 0,
        "context_compaction_attempts": 0,
        "emergency_compact_requested": False,
        "last_context_strategy": None,
        "is_sub_agent": False,
        "parent_task_id": None,
    }
    state.update(overrides)
    return state


class TestSerializeAgentState:
    """Tests for serialize_agent_state."""

    def test_messages_serialized_to_dicts(self):
        state = make_sample_state()
        result = serialize_agent_state(state)
        assert "messages" in result
        assert isinstance(result["messages"], list)
        assert len(result["messages"]) == 3
        # Messages should be dicts
        assert isinstance(result["messages"][0], dict)
        assert result["messages"][0]["type"] == "system"

    def test_scalar_fields_preserved(self):
        state = make_sample_state(task_id="task-123", current_turn=5)
        result = serialize_agent_state(state)
        assert result["task_id"] == "task-123"
        assert result["current_turn"] == 5

    def test_none_values_preserved(self):
        state = make_sample_state(final_result=None, error=None)
        result = serialize_agent_state(state)
        assert result["final_result"] is None
        assert result["error"] is None

    def test_tool_results_serialized(self):
        state = make_sample_state(tool_results={
            "call_1": {"tool_name": "read_file", "output": "content"}
        })
        result = serialize_agent_state(state)
        assert result["tool_results"]["call_1"]["tool_name"] == "read_file"

    def test_empty_messages_list(self):
        state = make_sample_state(messages=[])
        result = serialize_agent_state(state)
        assert result["messages"] == []


class TestDeserializeAgentState:
    """Tests for deserialize_agent_state."""

    def test_messages_restored_to_langchain_objects(self):
        state = make_sample_state()
        serialized = serialize_agent_state(state)
        restored = deserialize_agent_state(serialized)

        messages = restored["messages"]
        assert len(messages) == 3
        assert isinstance(messages[0], SystemMessage)
        assert isinstance(messages[1], HumanMessage)
        assert isinstance(messages[2], AIMessage)

    def test_scalar_fields_restored(self):
        state = make_sample_state(task_id="task-456", current_turn=7)
        serialized = serialize_agent_state(state)
        restored = deserialize_agent_state(serialized)

        assert restored["task_id"] == "task-456"
        assert restored["current_turn"] == 7
        assert restored["model"] == "gpt-4"

    def test_tool_results_restored(self):
        state = make_sample_state(tool_results={
            "call_1": {"status": "success", "output": "done"}
        })
        serialized = serialize_agent_state(state)
        restored = deserialize_agent_state(serialized)

        assert restored["tool_results"]["call_1"]["status"] == "success"

    def test_full_round_trip_preserves_all_fields(self):
        """After serialize → deserialize, all fields should match."""
        original = make_sample_state(
            current_turn=3,
            phase="planning",
            thinking_text="Let me think...",
            tool_results={"call_x": {"output": "result"}},
            pending_tool_calls=[{"name": "search", "args": {"q": "test"}}],
            last_executed_tool_call_ids=["call_x"],
        )
        serialized = serialize_agent_state(original)
        restored = deserialize_agent_state(serialized)

        # Compare all scalar and structured fields
        for key in original:
            if key == "messages":
                continue  # Messages convert to/from objects
            assert restored.get(key) == original.get(key), f"Mismatch on field: {key}"

        # Messages: count and types should match
        assert len(restored["messages"]) == len(original["messages"])
        assert type(restored["messages"][0]) == type(original["messages"][0])

    def test_restored_state_is_json_serializable_input(self):
        """The serialized output should be JSON-serializable for file storage."""
        import json

        state = make_sample_state()
        serialized = serialize_agent_state(state)
        # Should not raise
        json.dumps(serialized, default=str)

    def test_tool_message_round_trip(self):
        """ToolMessage should survive serialization round-trip."""
        state = make_sample_state(messages=[
            HumanMessage(content="Read file"),
            AIMessage(content="", tool_calls=[{"name": "read", "args": {}, "id": "call_1"}]),
            ToolMessage(content="file content", tool_call_id="call_1"),
            AIMessage(content="File says: file content"),
        ])
        serialized = serialize_agent_state(state)
        restored = deserialize_agent_state(serialized)

        assert len(restored["messages"]) == 4
        assert isinstance(restored["messages"][2], ToolMessage)
        assert restored["messages"][2].tool_call_id == "call_1"
