"""Tests for TaskCompletionService message kind detection and segments building."""

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage, ToolMessage

from src.application.services.task_completion_service import TaskCompletionService
from src.domain.aggregates.session.session_message import (
    MessageStatus,
    SessionMessage,
    SessionMessageRole,
)
from src.domain.aggregates.task.task import Task, TaskConfig, TaskStatus
from src.domain.services.tool_output_limits import MAX_TOOL_OUTPUT_SIZE


# ── _get_message_kind tests ──────────────────────────────────────────────────

class TestGetMessageKind:
    """Tests for _get_message_kind — unified message type detection."""

    def test_dict_with_tool_calls_is_ai(self):
        msg = {"role": "assistant", "content": "Let me check", "tool_calls": [{"id": "1", "name": "read"}]}
        assert TaskCompletionService._get_message_kind(msg) == "ai"

    def test_dict_with_assistant_role_is_ai(self):
        msg = {"role": "assistant", "content": "Hello"}
        assert TaskCompletionService._get_message_kind(msg) == "ai"

    def test_aimessage_object_is_ai(self):
        msg = AIMessage(content="Hello")
        assert TaskCompletionService._get_message_kind(msg) == "ai"

    def test_aimessage_with_tool_calls_is_ai(self):
        msg = AIMessage(content="", tool_calls=[{"id": "1", "name": "read", "args": {}}])
        assert TaskCompletionService._get_message_kind(msg) == "ai"

    def test_aimessagechunk_object_is_ai(self):
        msg = AIMessageChunk(content="streaming...")
        assert TaskCompletionService._get_message_kind(msg) == "ai"

    def test_dict_with_user_role_is_human(self):
        msg = {"role": "user", "content": "Hello"}
        assert TaskCompletionService._get_message_kind(msg) == "human"

    def test_human_message_object_is_human(self):
        msg = HumanMessage(content="Hello")
        assert TaskCompletionService._get_message_kind(msg) == "human"

    def test_dict_with_system_role_is_system(self):
        msg = {"role": "system", "content": "You are helpful"}
        assert TaskCompletionService._get_message_kind(msg) == "system"

    def test_system_message_object_is_system(self):
        msg = SystemMessage(content="You are helpful")
        assert TaskCompletionService._get_message_kind(msg) == "system"

    def test_dict_with_tool_role_is_tool(self):
        msg = {"role": "tool", "content": "file content here"}
        assert TaskCompletionService._get_message_kind(msg) == "tool"

    def test_tool_message_object_is_tool(self):
        msg = ToolMessage(content="file content here", tool_call_id="abc")
        assert TaskCompletionService._get_message_kind(msg) == "tool"

    def test_function_message_object_is_tool(self):
        from langchain_core.messages import FunctionMessage
        msg = FunctionMessage(content="result", name="calc")
        assert TaskCompletionService._get_message_kind(msg) == "tool"

    def test_dict_with_dict_human_role_is_human(self):
        msg = {"role": "human", "content": "Hello"}
        assert TaskCompletionService._get_message_kind(msg) == "human"

    def test_unknown_type_returns_unknown(self):
        msg = object()
        assert TaskCompletionService._get_message_kind(msg) == "unknown"

    def test_dict_without_role_returns_unknown(self):
        msg = {"content": "no role field"}
        assert TaskCompletionService._get_message_kind(msg) == "unknown"


# ── _build_segments tests ────────────────────────────────────────────────────

class TestBuildSegments:
    """Tests for _build_segments — constructing timeline segments from messages."""

    def test_single_round_react(self):
        """A single ReAct round: AI text + tool call."""
        messages = [
            HumanMessage(content="read the file"),
            AIMessage(content="Let me check", tool_calls=[{"id": "tc1", "name": "read_file", "args": {"path": "/tmp/a"}}]),
            ToolMessage(content="file contents", tool_call_id="tc1"),
        ]
        tool_results = [{"id": "tc1", "tool_name": "read_file", "status": "success", "result": "file contents"}]

        segments = TaskCompletionService._build_segments(messages, "", tool_results)

        assert len(segments) == 2
        assert segments[0] == {"type": "text", "content": "Let me check"}
        assert segments[1]["type"] == "tool"
        assert segments[1]["content"] == "read_file"
        assert segments[1]["toolStatus"] == "success"
        assert segments[1]["toolResult"] == "file contents"

    def test_multi_round_react(self):
        """Multi-round ReAct: text → tool → text → tool."""
        messages = [
            HumanMessage(content="read and write files"),
            AIMessage(content="Reading first", tool_calls=[{"id": "tc1", "name": "read_file", "args": {"path": "/a"}}]),
            ToolMessage(content="a contents", tool_call_id="tc1"),
            AIMessage(content="Now writing", tool_calls=[{"id": "tc2", "name": "write_file", "args": {"path": "/b"}}]),
            ToolMessage(content="written", tool_call_id="tc2"),
        ]
        tool_results = [
            {"id": "tc1", "tool_name": "read_file", "status": "success", "result": "a contents"},
            {"id": "tc2", "tool_name": "write_file", "status": "success", "result": "written"},
        ]

        segments = TaskCompletionService._build_segments(messages, "", tool_results)

        assert len(segments) == 4
        assert segments[0]["type"] == "text"
        assert segments[0]["content"] == "Reading first"
        assert segments[1]["type"] == "tool"
        assert segments[1]["content"] == "read_file"
        assert segments[2]["type"] == "text"
        assert segments[2]["content"] == "Now writing"
        assert segments[3]["type"] == "tool"
        assert segments[3]["content"] == "write_file"

    def test_thinking_text_at_start(self):
        """Thinking content appears as first segment."""
        messages = [
            HumanMessage(content="analyze"),
            AIMessage(content="Analysis results", tool_calls=[]),
        ]

        segments = TaskCompletionService._build_segments(messages, "Step by step reasoning...", [])

        assert len(segments) == 2
        assert segments[0] == {"type": "thinking", "content": "Step by step reasoning..."}
        assert segments[1] == {"type": "text", "content": "Analysis results"}

    def test_no_thinking_text(self):
        """When thinking_text is empty, no thinking segment is created."""
        messages = [AIMessage(content="Direct answer")]

        segments = TaskCompletionService._build_segments(messages, "", [])

        assert len(segments) == 1
        assert segments[0]["type"] == "text"

    def test_skips_human_and_system_messages(self):
        """Human and system messages do not produce segments."""
        messages = [
            SystemMessage(content="Be helpful"),
            HumanMessage(content="hello"),
            AIMessage(content="Hi there"),
        ]

        segments = TaskCompletionService._build_segments(messages, "", [])

        assert len(segments) == 1
        assert segments[0]["content"] == "Hi there"

    def test_missing_tool_result_defaults_to_success(self):
        """When a tool call has no matching result, defaults to success with empty result."""
        messages = [
            AIMessage(content="", tool_calls=[{"id": "tc1", "name": "unknown_tool", "args": {}}]),
        ]

        segments = TaskCompletionService._build_segments(messages, "", [])

        assert len(segments) == 1
        assert segments[0]["type"] == "tool"
        assert segments[0]["toolStatus"] == "success"
        assert segments[0]["toolResult"] == ""

    def test_empty_tool_call_id_is_skipped(self):
        """Tool calls with empty or missing id are skipped with a warning."""
        messages = [
            AIMessage(content="Let me try", tool_calls=[{"id": "", "name": "bad_tool", "args": {}}]),
        ]

        segments = TaskCompletionService._build_segments(messages, "", [])

        # Content text segment should still be present; bad tool call is skipped
        assert segments[0]["type"] == "text"
        assert segments[0]["content"] == "Let me try"
        # No tool segment for the empty-id tool call
        assert len([s for s in segments if s["type"] == "tool"]) == 0

    def test_clarify_output_in_messages(self):
        """Messages including clarify tool output should build correct segments."""
        messages = [
            HumanMessage(content="do something"),
            AIMessage(
                content="I need more info",
                tool_calls=[{"id": "tc1", "name": "clarify", "args": {"question": "which file?"}}],
            ),
        ]
        tool_results = [{"id": "tc1", "tool_name": "clarify", "status": "success", "result": "which file?"}]

        segments = TaskCompletionService._build_segments(messages, "", tool_results)

        assert len(segments) == 2
        assert segments[0]["type"] == "text"
        assert segments[0]["content"] == "I need more info"
        assert segments[1]["type"] == "tool"
        assert segments[1]["content"] == "clarify"


# ── Tool output truncation in finalize() tests ────────────────────────────────


class FakeMessageRepo:
    """Captures saved SessionMessages for assertions."""

    def __init__(self):
        self.saved: list[SessionMessage] = []

    async def add(self, message: SessionMessage) -> SessionMessage:
        self.saved.append(message)
        return message


@pytest.mark.asyncio
async def test_finalize_truncates_large_tool_results():
    """finalize() truncates tool output > MAX_TOOL_OUTPUT_SIZE in all_tool_results."""
    message_repo = FakeMessageRepo()
    service = TaskCompletionService(message_repo=message_repo)

    large_output = "z" * 100_000
    task = Task(
        id="task-1", message="test", workspace="/tmp",
        status=TaskStatus.RUNNING, model="gpt-4",
        config=TaskConfig(max_turns=10), max_turns=10,
        agent_id="agent-1", session_id="session-1",
    )

    await service.finalize(
        task=task,
        session_id="session-1",
        result={
            "messages": [AIMessage(content="Done", tool_calls=[])],
            "current_turn": 1,
            "phase": "complete",
            "tool_results": {
                "tc-1": {
                    "tool_name": "read_file",
                    "status": "success",
                    "output": large_output,
                }
            },
        },
        persist_session_messages=True,
    )

    assert len(message_repo.saved) == 1
    saved_msg = message_repo.saved[0]
    assert len(saved_msg.tool_results) == 1
    tr = saved_msg.tool_results[0]
    assert len(tr["result"]) < len(large_output)
    assert "[truncated:" in tr["result"]


@pytest.mark.asyncio
async def test_finalize_keeps_small_tool_results_unchanged():
    """finalize() does not truncate tool output under the limit."""
    message_repo = FakeMessageRepo()
    service = TaskCompletionService(message_repo=message_repo)

    small_output = "small result"
    task = Task(
        id="task-1", message="test", workspace="/tmp",
        status=TaskStatus.RUNNING, model="gpt-4",
        config=TaskConfig(max_turns=10), max_turns=10,
        agent_id="agent-1", session_id="session-1",
    )

    await service.finalize(
        task=task,
        session_id="session-1",
        result={
            "messages": [AIMessage(content="Done", tool_calls=[])],
            "current_turn": 1,
            "phase": "complete",
            "tool_results": {
                "tc-1": {
                    "tool_name": "read_file",
                    "status": "success",
                    "output": small_output,
                }
            },
        },
        persist_session_messages=True,
    )

    saved_msg = message_repo.saved[0]
    assert saved_msg.tool_results[0]["result"] == small_output
