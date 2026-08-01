"""Tests for tool output truncation utility."""

import pytest

from src.domain.services.tool_output_limits import MAX_TOOL_OUTPUT_SIZE, truncate_tool_output


class TestTruncateToolOutput:
    """Tests for truncate_tool_output function."""

    def test_output_under_limit_unchanged(self):
        output = "short output"
        result = truncate_tool_output(output)
        assert result == "short output"

    def test_output_exactly_at_limit_unchanged(self):
        output = "x" * MAX_TOOL_OUTPUT_SIZE
        result = truncate_tool_output(output)
        assert result == output

    def test_output_over_limit_truncated_with_marker(self):
        output = "x" * 100_000
        result = truncate_tool_output(output)
        assert len(result) == MAX_TOOL_OUTPUT_SIZE + len(
            f"\n\n[truncated: 100000 chars → {MAX_TOOL_OUTPUT_SIZE} chars]"
        )
        assert result.startswith("x" * MAX_TOOL_OUTPUT_SIZE)
        assert "[truncated:" in result
        assert "100000" in result

    def test_empty_string_unchanged(self):
        result = truncate_tool_output("")
        assert result == ""

    def test_none_returns_empty_string(self):
        result = truncate_tool_output(None)
        assert result == ""

    def test_just_over_limit_truncated(self):
        output = "a" * (MAX_TOOL_OUTPUT_SIZE + 1)
        result = truncate_tool_output(output)
        assert "[truncated:" in result
        assert output not in result
