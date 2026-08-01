"""Tests for tool_results merge reducer."""

from src.domain.agent_loop.state import _merge_tool_results


class TestMergeToolResults:
    """Tests for _merge_tool_results reducer."""

    def test_merges_two_non_overlapping_dicts(self):
        left = {"call_1": {"tool_name": "read", "output": "a"}}
        right = {"call_2": {"tool_name": "search", "output": "b"}}

        result = _merge_tool_results(left, right)

        assert len(result) == 2
        assert result["call_1"]["output"] == "a"
        assert result["call_2"]["output"] == "b"

    def test_right_overwrites_left_on_key_conflict(self):
        """When same tool_call_id appears, right (newer) wins."""
        left = {"call_1": {"output": "old"}}
        right = {"call_1": {"output": "new"}}

        result = _merge_tool_results(left, right)

        assert len(result) == 1
        assert result["call_1"]["output"] == "new"

    def test_left_empty_returns_right(self):
        result = _merge_tool_results({}, {"call_1": {"output": "x"}})
        assert result == {"call_1": {"output": "x"}}

    def test_right_empty_returns_left(self):
        result = _merge_tool_results({"call_1": {"output": "x"}}, {})
        assert result == {"call_1": {"output": "x"}}

    def test_both_empty_returns_empty(self):
        result = _merge_tool_results({}, {})
        assert result == {}

    def test_accumulates_across_multiple_turns(self):
        """Simulate 3 turns of tool execution."""
        turn1 = {"call_1": {"output": "t1"}}
        turn2 = {"call_2": {"output": "t2"}, "call_3": {"output": "t3"}}
        turn3 = {"call_4": {"output": "t4"}}

        state = {}
        state = _merge_tool_results(state, turn1)
        state = _merge_tool_results(state, turn2)
        state = _merge_tool_results(state, turn3)

        assert len(state) == 4
        assert "call_1" in state
        assert "call_2" in state
        assert "call_3" in state
        assert "call_4" in state
