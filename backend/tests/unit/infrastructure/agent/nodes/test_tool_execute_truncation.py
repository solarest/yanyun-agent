"""Tests for tool output truncation in tool_execute_node."""

import pytest

from src.domain.entities.tool import ToolContext, ToolResult
from src.infrastructure.agent.nodes.tool_execute_node import _execute_single_tool


class FakeToolRegistry:
    """Returns a ToolResult with configurable output."""

    def __init__(self, output: str):
        self.output = output

    async def execute(self, tool_name: str, tool_input: dict, context: ToolContext) -> ToolResult:
        return ToolResult(success=True, output=self.output, error=None)


class NoopEmitter:
    """Event emitter that records calls without side effects."""

    def __init__(self):
        self.calls = []

    async def emit(self, task_id: str, event_type: str, payload: dict) -> None:
        self.calls.append((task_id, event_type, payload))


@pytest.mark.asyncio
async def test_sse_event_has_truncated_output():
    """When tool output exceeds limit, the SSE tool:result event payload is truncated."""
    large_output = "y" * 200_000
    registry = FakeToolRegistry(output=large_output)
    emitter = NoopEmitter()
    context = ToolContext(task_id="task-1", workspace="/tmp", extra={})

    await _execute_single_tool(
        tool_registry=registry,
        event_emitter=emitter,
        task_id="task-1",
        tc={"id": "tc-1", "name": "cat", "input": {"command": "cat huge.log"}},
        context=context,
    )

    result_events = [c for c in emitter.calls if c[1] == "tool:result"]
    assert len(result_events) == 1
    _, _, result_payload = result_events[0]
    assert "output" in result_payload
    assert "[truncated:" in result_payload["output"]


@pytest.mark.asyncio
async def test_result_dict_keeps_full_output_for_langgraph():
    """result_dict output is NOT truncated — LLM needs full content for reasoning."""
    large_output = "x" * 200_000
    registry = FakeToolRegistry(output=large_output)
    emitter = NoopEmitter()
    context = ToolContext(task_id="task-1", workspace="/tmp", extra={})

    _, result_dict = await _execute_single_tool(
        tool_registry=registry,
        event_emitter=emitter,
        task_id="task-1",
        tc={"id": "tc-1", "name": "read_file", "input": {"path": "/tmp/large"}},
        context=context,
    )

    assert result_dict["output"] == large_output
    assert "[truncated:" not in result_dict["output"]


@pytest.mark.asyncio
async def test_small_output_passes_through_both_paths():
    """Small output unchanged in both SSE event and result_dict."""
    small_output = "small result"
    registry = FakeToolRegistry(output=small_output)
    emitter = NoopEmitter()
    context = ToolContext(task_id="task-1", workspace="/tmp", extra={})

    _, result_dict = await _execute_single_tool(
        tool_registry=registry,
        event_emitter=emitter,
        task_id="task-1",
        tc={"id": "tc-1", "name": "read_file", "input": {}},
        context=context,
    )

    assert result_dict["output"] == "small result"
    result_events = [c for c in emitter.calls if c[1] == "tool:result"]
    assert len(result_events) == 1
    _, _, result_payload = result_events[0]
    assert result_payload["output"] == "small result"
    assert "[truncated:" not in result_payload["output"]
