from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, RemoveMessage, SystemMessage

from src.infrastructure.agent.nodes.context_compact_node import context_compact_node
from src.infrastructure.agent.nodes.llm_call_node import llm_call_node
from src.infrastructure.agent.nodes.loop_detect_node import loop_detect_node
from src.infrastructure.agent.nodes.stuck_detect_node import stuck_detect_node
from src.infrastructure.agent.nodes.tool_execute_node import tool_execute_node


class RecordingEmitter:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def emit(self, task_id: str, event_type: str, payload: dict) -> None:
        self.events.append(
            {"task_id": task_id, "event_type": event_type, "payload": payload}
        )

    async def emit_phase_changed(
        self,
        task_id: str,
        new_phase: str,
        previous_phase: str,
        turn: int,
    ) -> None:
        await self.emit(
            task_id,
            "phase:changed",
            {
                "phase": new_phase,
                "previousPhase": previous_phase,
                "turn": turn,
            },
        )

    async def emit_llm_chunk(self, task_id: str, turn: int, text: str) -> None:
        await self.emit(
            task_id,
            "llm:chunk",
            {"turn": turn, "text": text, "delta": True},
        )


class FakeLLM:
    async def astream(self, messages, **kwargs):
        self.messages = messages
        yield AIMessageChunk(content="Hello")
        yield AIMessageChunk(content=" world")


def make_state(**overrides):
    state = {
        "messages": [],
        "task_id": "task-1",
        "workspace": "/tmp",
        "user_message": "hello",
        "task_start_message_count": 0,
        "current_turn": 0,
        "max_turns": 5,
        "phase": "idle",
        "should_end": False,
        "is_complete": False,
        "pending_tool_calls": [],
        "tool_results": {},
        "awaiting_user_input": False,
        "last_executed_tool_call_ids": [],
        "loop_detection_count": 0,
        "loop_detected": False,
        "loop_type": None,
        "stuck_detection_count": 0,
        "stuck_detected": False,
        "stuck_type": None,
        "current_llm_text": "",
        "system_prompt": "",
        "final_result": None,
        "error": None,
    }
    state.update(overrides)
    return state


@pytest.mark.asyncio
async def test_llm_call_node_emits_phase_chunks_and_completion() -> None:
    emitter = RecordingEmitter()
    llm = FakeLLM()

    result = await llm_call_node(
        make_state(system_prompt="system prompt"),
        {"configurable": {"llm": llm, "event_emitter": emitter, "agent_id": "agent-1"}},
    )

    assert [event["event_type"] for event in emitter.events] == [
        "phase:changed",
        "llm:chunk",
        "llm:chunk",
        "llm:complete",
    ]
    assert isinstance(llm.messages[0], SystemMessage)
    assert result["messages"][0].content == "Hello world"
    assert result["phase"] == "thinking"
    assert result["current_turn"] == 1
    assert result["last_executed_tool_call_ids"] == []


@pytest.mark.asyncio
async def test_tool_execute_node_emits_phase_call_and_result() -> None:
    emitter = RecordingEmitter()

    class FakeToolRegistry:
        async def execute(self, tool_name, tool_input, context):
            assert tool_name == "search"
            assert tool_input == {"q": "hello"}
            assert context.task_id == "task-1"
            return SimpleNamespace(
                output="done",
                success=True,
                error=None,
                metadata={},
            )

    result = await tool_execute_node(
        make_state(
            phase="thinking",
            current_turn=2,
            pending_tool_calls=[
                {"id": "call-1", "name": "search", "input": {"q": "hello"}}],
        ),
        {"configurable": {"tool_registry": FakeToolRegistry(), "event_emitter": emitter}},
    )

    assert [event["event_type"] for event in emitter.events] == [
        "phase:changed",
        "tool:call",
        "tool:result",
    ]
    assert result["phase"] == "tool_executing"
    assert result["tool_results"] == {
        "call-1": {
            "tool_name": "search",
            "status": "success",
            "output": "done",
            "error": None,
            "metadata": {},
        }
    }


@pytest.mark.asyncio
async def test_tool_execute_node_marks_awaiting_user_input_for_clarify_like_tools() -> None:
    emitter = RecordingEmitter()

    class FakeToolRegistry:
        async def execute(self, tool_name, tool_input, context):
            return SimpleNamespace(
                output="**Question**: Which option?",
                success=True,
                error=None,
                metadata={"awaiting_user_input": True},
            )

    result = await tool_execute_node(
        make_state(
            phase="thinking",
            current_turn=1,
            pending_tool_calls=[
                {"id": "call-clarify", "name": "clarify", "input": {"question": "?"}}],
        ),
        {"configurable": {"tool_registry": FakeToolRegistry(), "event_emitter": emitter}},
    )

    assert result["awaiting_user_input"] is True
    assert result["final_result"] == "**Question**: Which option?"


@pytest.mark.asyncio
async def test_tool_execute_node_preserves_previous_tool_results() -> None:
    emitter = RecordingEmitter()

    class FakeToolRegistry:
        async def execute(self, tool_name, tool_input, context):
            return SimpleNamespace(
                output="fresh result",
                success=True,
                error=None,
                metadata={},
            )

    result = await tool_execute_node(
        make_state(
            tool_results={
                "call-old": {
                    "tool_name": "file_read",
                    "status": "success",
                    "output": "old result",
                    "error": None,
                    "metadata": {},
                }
            },
            pending_tool_calls=[
                {"id": "call-new", "name": "search", "input": {"q": "hello"}}],
        ),
        {"configurable": {"tool_registry": FakeToolRegistry(), "event_emitter": emitter}},
    )

    assert result["tool_results"] == {
        "call-old": {
            "tool_name": "file_read",
            "status": "success",
            "output": "old result",
            "error": None,
            "metadata": {},
        },
        "call-new": {
            "tool_name": "search",
            "status": "success",
            "output": "fresh result",
            "error": None,
            "metadata": {},
        },
    }


@pytest.mark.asyncio
async def test_tool_execute_node_executes_all_tools_uniformly() -> None:
    """plan 优先级已移除，所有工具统一执行"""
    emitter = RecordingEmitter()
    executed_tools: list[str] = []

    class FakeToolRegistry:
        async def execute(self, tool_name, tool_input, context):
            executed_tools.append(tool_name)
            return SimpleNamespace(
                output="plan created",
                success=True,
                error=None,
                metadata={
                    "type": "plan",
                    "goal": "goal",
                    "execution_order": [1],
                    "steps": [{"id": 1, "description": "step"}],
                },
            )

    result = await tool_execute_node(
        make_state(
            pending_tool_calls=[
                {"id": "call-search", "name": "web_search",
                    "input": {"query": "news"}},
                {"id": "call-plan", "name": "plan",
                    "input": {"goal": "goal", "steps": ["step"]}},
            ],
        ),
        {"configurable": {"tool_registry": FakeToolRegistry(), "event_emitter": emitter}},
    )

    # 所有工具均被执行（不再有 plan 优先级跳过逻辑）
    assert executed_tools == ["web_search", "plan"]
    assert result["last_executed_tool_call_ids"] == [
        "call-search", "call-plan"]
    assert result["tool_results"]["call-search"]["status"] == "success"
    assert result["tool_results"]["call-plan"]["status"] == "success"


@pytest.mark.asyncio
async def test_loop_detect_node_emits_loop_detected_and_phase_change() -> None:
    emitter = RecordingEmitter()

    result = await loop_detect_node(
        make_state(
            phase="thinking",
            current_turn=3,
            messages=[
                {"role": "assistant", "tool_calls": [
                    {"name": "search", "args": {"q": "x"}}]},
                {"role": "assistant", "tool_calls": [
                    {"name": "search", "args": {"q": "x"}}]},
                {"role": "assistant", "tool_calls": [
                    {"name": "search", "args": {"q": "x"}}]},
            ],
        ),
        {"configurable": {"event_emitter": emitter}},
    )

    assert [event["event_type"] for event in emitter.events] == [
        "loop:detected",
        "phase:changed",
    ]
    assert result["loop_detected"] is True
    assert result["loop_type"] == "exact_tool_repeat"
    assert result["phase"] == "loop_correcting"


@pytest.mark.asyncio
async def test_loop_detect_invalid_tool_calls() -> None:
    """测试无效工具调用检测（缺少 name 或 id）"""
    emitter = RecordingEmitter()

    result = await loop_detect_node(
        make_state(
            pending_tool_calls=[
                {"id": "", "name": "search", "input": {"q": "x"}},  # 缺少 id
            ],
        ),
        {"configurable": {"event_emitter": emitter}},
    )

    assert result["loop_detected"] is True
    assert result["loop_type"] == "invalid_tool_call"
    assert result["loop_detection_count"] == 1
    assert result["phase"] == "loop_correcting"


@pytest.mark.asyncio
async def test_loop_detect_alternating_pattern() -> None:
    """测试 A-B-A-B 交替模式检测"""
    emitter = RecordingEmitter()

    result = await loop_detect_node(
        make_state(
            messages=[
                {"role": "assistant", "tool_calls": [
                    {"name": "read_file", "args": {"path": "a.txt"}}]},
                {"role": "assistant", "tool_calls": [
                    {"name": "grep_search", "args": {"query": "x"}}]},
                {"role": "assistant", "tool_calls": [
                    {"name": "read_file", "args": {"path": "a.txt"}}]},
                {"role": "assistant", "tool_calls": [
                    {"name": "grep_search", "args": {"query": "x"}}]},
            ],
        ),
        {"configurable": {"event_emitter": emitter}},
    )

    assert result["loop_detected"] is True
    assert result["loop_type"] == "alternating_pattern"
    assert result["phase"] == "loop_correcting"


@pytest.mark.asyncio
async def test_loop_detect_node_ignores_tool_history_before_current_task() -> None:
    emitter = RecordingEmitter()

    result = await loop_detect_node(
        make_state(
            task_start_message_count=3,
            messages=[
                {"role": "assistant", "tool_calls": [
                    {"name": "search", "args": {"q": "x"}}]},
                {"role": "assistant", "tool_calls": [
                    {"name": "search", "args": {"q": "x"}}]},
                {"role": "assistant", "tool_calls": [
                    {"name": "search", "args": {"q": "x"}}]},
                {"role": "assistant", "content": "new run", "tool_calls": [
                    {"name": "search", "args": {"q": "y"}}]},
            ],
        ),
        {"configurable": {"event_emitter": emitter}},
    )

    assert result["loop_detected"] is False
    assert emitter.events == []


@pytest.mark.asyncio
async def test_stuck_detect_node_emits_stuck_detected_and_phase_change() -> None:
    emitter = RecordingEmitter()

    result = await stuck_detect_node(
        make_state(
            phase="thinking",
            current_turn=2,
            messages=[
                {"role": "assistant", "content": "thinking 1", "tool_calls": []},
                {"role": "assistant", "content": "thinking 2", "tool_calls": []},
                {"role": "assistant", "content": "thinking 3", "tool_calls": []},
            ],
        ),
        {"configurable": {"event_emitter": emitter}},
    )

    assert [event["event_type"] for event in emitter.events] == [
        "stuck:detected",
        "phase:changed",
    ]
    assert result["stuck_detected"] is True
    assert result["phase"] == "stuck_recovering"


@pytest.mark.asyncio
async def test_stuck_detect_node_ignores_text_history_before_current_task() -> None:
    emitter = RecordingEmitter()

    result = await stuck_detect_node(
        make_state(
            task_start_message_count=3,
            messages=[
                {"role": "assistant", "content": "old 1", "tool_calls": []},
                {"role": "assistant", "content": "old 2", "tool_calls": []},
                {"role": "assistant", "content": "old 3", "tool_calls": []},
                {"role": "assistant", "content": "new answer", "tool_calls": []},
            ],
        ),
        {"configurable": {"event_emitter": emitter}},
    )

    # 只有1条新的 assistant消息,不应检测到 stuck
    assert result.get("stuck_detected") is None or result.get(
        "stuck_detected") is False
    assert emitter.events == []


@pytest.mark.asyncio
async def test_context_compact_node_emits_phase_and_compaction_event() -> None:
    emitter = RecordingEmitter()
    # 使用真实 LangChain 消息对象（带 id）以测试 RemoveMessage 逻辑
    messages = [
        AIMessage(content=f"msg-{i}", id=f"msg-id-{i}") for i in range(12)]

    result = await context_compact_node(
        make_state(messages=messages, phase="thinking", current_turn=4),
        {"configurable": {"event_emitter": emitter}},
    )

    assert [event["event_type"] for event in emitter.events] == [
        "phase:changed",
        "context:compacting",
    ]
    assert result["phase"] == "context_compacting"
    # 应该删除 messages[1:-10]（即 msg-1），保留第 1 条和最近 10 条
    assert all(isinstance(m, RemoveMessage) for m in result["messages"])
    # 12 - 1(first) - 10(recent) = 1 to remove
    assert len(result["messages"]) == 1
