"""Tests for DB-specific tool output truncation with file_ref."""

import pytest

from src.domain.services.tool_output_limits import (
    MAX_TOOL_OUTPUT_SIZE,
    truncate_tool_output_for_db,
)


class TestTruncateToolOutputForDb:
    """Tests for DB truncation with full_result_ref."""

    def test_output_under_limit_unchanged_no_ref(self):
        result = truncate_tool_output_for_db("short output", ref="results/call_1.txt")
        assert result["result"] == "short output"
        assert "full_result_ref" not in result

    def test_output_over_limit_truncated_with_ref(self):
        output = "x" * 100_000
        result = truncate_tool_output_for_db(output, ref="results/call_1.txt")

        assert "[truncated:" in result["result"]
        assert result["full_result_ref"] == "results/call_1.txt"
        assert len(result["result"]) == MAX_TOOL_OUTPUT_SIZE + len(
            f"\n\n[truncated: 100000 chars → {MAX_TOOL_OUTPUT_SIZE} chars]"
        )

    def test_none_output_returns_empty_no_ref(self):
        result = truncate_tool_output_for_db(None, ref="results/call_1.txt")
        assert result["result"] == ""
        assert "full_result_ref" not in result

    def test_empty_output_no_ref(self):
        result = truncate_tool_output_for_db("", ref="results/call_1.txt")
        assert result["result"] == ""
        assert "full_result_ref" not in result

    def test_exact_limit_no_truncation_no_ref(self):
        output = "a" * MAX_TOOL_OUTPUT_SIZE
        result = truncate_tool_output_for_db(output, ref="results/call_1.txt")
        assert result["result"] == output
        assert "full_result_ref" not in result

    def test_ref_is_none_still_truncates_without_ref(self):
        """When ref is None, still truncate but don't add full_result_ref."""
        output = "x" * 100_000
        result = truncate_tool_output_for_db(output, ref=None)
        assert "[truncated:" in result["result"]
        assert "full_result_ref" not in result
