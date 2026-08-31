from types import SimpleNamespace

import pytest
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from src.infrastructure.agent.nodes.context_compact_node import context_compact_node
from src.infrastructure.agent.nodes.llm_call_node import llm_call_node
from src.infrastructure.agent.nodes.tool_execute_node import tool_execute_node
from src.domain.entities.event_types import AgentEventType
from src.infrastructure.tools.confirmation.contract import CONFIRMATION_METADATA_KEY


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
            AgentEventType.PHASE_CHANGED,
            {
                "phase": new_phase,
                "previousPhase": previous_phase,
                "turn": turn,
            },
        )

    async def emit_llm_chunk(self, task_id: str, turn: int, text: str) -> None:
        await self.emit(
            task_id,
            AgentEventType.LLM_CHUNK,
            {"turn": turn, "text": text, "delta": True},
        )

    async def emit_thinking_chunk(self, task_id: str, turn: int, text: str) -> None:
        await self.emit(
            task_id,
            AgentEventType.THINKING_CHUNK,
            {"turn": turn, "text": text, "delta": True},
        )

    async def emit_safe(self, task_id: str, event_type: str, payload: dict) -> None:
        """安全发射事件（测试实现）"""
        await self.emit(task_id, event_type, payload)

    async def emit_phase_changed_safe(
        self,
        task_id: str,
        new_phase: str,
        previous_phase: str,
        turn: int,
    ) -> None:
        """安全发射阶段变更事件（测试实现）"""
        await self.emit_phase_changed(task_id, new_phase, previous_phase, turn)


class FakeLLM:
    async def astream(self, messages, **kwargs):
        self.messages = messages
        yield AIMessageChunk(content="Hello")
        yield AIMessageChunk(content=" world")


class ToolCallingLLM:
    async def astream(self, messages, **kwargs):
        yield AIMessageChunk(
            content="",
            tool_calls=[{"id": "call-search", "name": "search", "args": {"q": "latest"}}],
        )


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
        "current_llm_text": "",
        "system_prompt": "",
        "final_result": None,
        "error": None,
        # === 上下文管理 ===
        "max_context_tokens": 128_000,
        "context_token_estimate": 0,
        "context_token_baseline": None,
        "context_token_baseline_message_count": 0,
        "context_compaction_attempts": 0,
        "emergency_compact_requested": False,
        "last_context_strategy": None,
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
        AgentEventType.PHASE_CHANGED,
        AgentEventType.LLM_CHUNK,
        AgentEventType.LLM_CHUNK,
        AgentEventType.LLM_COMPLETE,
    ]
    assert isinstance(llm.messages[0], SystemMessage)
    assert result["messages"][0].content == "Hello world"
    # 无 tool_calls 时,标记为 complete
    assert result["phase"] == "complete"
    assert result["should_end"] is True
    assert result["is_complete"] is True
    assert result["current_turn"] == 1
    assert result["last_executed_tool_call_ids"] == []


@pytest.mark.asyncio
async def test_llm_call_node_clears_recoverable_context_limit_error_after_success() -> None:
    """紧急压缩后的成功 LLM 调用必须清除上一轮留下的可恢复错误。"""
    result = await llm_call_node(
        make_state(
            error="context window exceeded",
            context_compaction_attempts=1,
        ),
        {"configurable": {"llm": FakeLLM(), "event_emitter": RecordingEmitter()}},
    )

    assert result["error"] is None


@pytest.mark.asyncio
async def test_llm_call_node_ends_after_reaching_turn_budget() -> None:
    """达到 max_turns 的本轮不得继续进入工具循环。"""
    result = await llm_call_node(
        make_state(current_turn=4, max_turns=5),
        {"configurable": {"llm": ToolCallingLLM(), "event_emitter": RecordingEmitter()}},
    )

    assert result["current_turn"] == 5
    assert result["pending_tool_calls"]
    assert result["should_end"] is True


@pytest.mark.asyncio
async def test_llm_call_node_keeps_result_when_chunk_event_emission_fails() -> None:
    """流式观测失败不得让已经获得的 LLM 输出整轮失效。"""

    class FailingChunkEmitter(RecordingEmitter):
        async def emit_llm_chunk(self, task_id: str, turn: int, text: str) -> None:
            raise OSError("event storage unavailable")

    result = await llm_call_node(
        make_state(),
        {"configurable": {"llm": FakeLLM(), "event_emitter": FailingChunkEmitter()}},
    )

    assert result["messages"][0].content == "Hello world"
    assert result["should_end"] is True


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
        AgentEventType.PHASE_CHANGED,
        AgentEventType.TOOL_CALL,
        AgentEventType.TOOL_RESULT,
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
async def test_tool_execute_node_preserves_large_tool_output_for_llm_context() -> None:
    emitter = RecordingEmitter()
    large_output = "x" * 20000

    class FakeToolRegistry:
        async def execute(self, tool_name, tool_input, context):
            return SimpleNamespace(
                output=large_output,
                success=True,
                error=None,
                metadata={},
            )

    result = await tool_execute_node(
        make_state(
            pending_tool_calls=[
                {"id": "call-large", "name": "file_read",
                    "input": {"path": "logs/tool-call.log"}},
            ],
        ),
        {"configurable": {"tool_registry": FakeToolRegistry(), "event_emitter": emitter}},
    )

    tool_result = result["tool_results"]["call-large"]
    assert tool_result["output"] == large_output
    assert tool_result["metadata"] == {}
    assert result["messages"][0].content == large_output


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
async def test_tool_execute_node_executes_one_tool_and_keeps_the_rest_pending() -> None:
    """工具节点一次只执行一个调用，剩余调用由图路由回本节点。"""
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

    assert executed_tools == ["web_search"]
    assert result["last_executed_tool_call_ids"] == ["call-search"]
    assert result["tool_results"]["call-search"]["status"] == "success"
    assert result["pending_tool_calls"] == [
        {"id": "call-plan", "name": "plan", "input": {"goal": "goal", "steps": ["step"]}},
    ]


@pytest.mark.asyncio
async def test_confirmation_is_persistable_and_denial_does_not_repeat_tool() -> None:
    """确认等待和拒绝都由普通 AgentState 表示，不使用图中断。"""
    emitter = RecordingEmitter()
    confirmation_checks: list[str] = []
    executed_tools: list[str] = []

    class FakeToolRegistry:
        async def execute(self, tool_name, tool_input, context):
            if context.extra.get("bypass_confirmation"):
                executed_tools.append(tool_name)
                return SimpleNamespace(
                    output="executed",
                    success=True,
                    error=None,
                    metadata={},
                )
            confirmation_checks.append(tool_name)
            if tool_name == "dangerous":
                return SimpleNamespace(
                    output=None,
                    success=False,
                    error="confirmation_required",
                    metadata={
                        CONFIRMATION_METADATA_KEY: True,
                        "tool_call_id": "call-dangerous",
                        "command": "rm important-file",
                        "category": "destructive",
                        "risk_reason": "destructive operation",
                    },
                )
            return SimpleNamespace(
                output="safe result",
                success=True,
                error=None,
                metadata={},
            )

    state = make_state(
        pending_tool_calls=[
            {"id": "call-dangerous", "name": "dangerous", "input": {}},
        ],
    )
    config = {
        "configurable": {
            "tool_registry": FakeToolRegistry(),
            "event_emitter": emitter,
        }
    }

    pending = await tool_execute_node(state, config)
    denied = await tool_execute_node(
        state,
        {
            "configurable": {
                **config["configurable"],
                "approval": {
                    "tool_call_id": "call-dangerous",
                    "decision": "deny",
                },
            }
        },
    )

    assert pending["pending_confirmation"]["tool_call_id"] == "call-dangerous"
    assert pending["pending_tool_calls"][0]["id"] == "call-dangerous"
    assert confirmation_checks == ["dangerous", "dangerous"]
    assert executed_tools == []
    assert denied["tool_results"]["call-dangerous"]["error"] == "user_denied"


@pytest.mark.asyncio
async def test_context_compact_node_skip_when_below_watermark() -> None:
    """Token 低于 40% 水线时，只发 skip 事件，不改消息"""
    emitter = RecordingEmitter()
    messages = [
        AIMessage(content=f"msg-{i}", id=f"msg-id-{i}") for i in range(12)
    ]

    result = await context_compact_node(
        make_state(
            messages=messages, phase="thinking", current_turn=4,
            max_context_tokens=128_000,
        ),
        {"configurable": {"event_emitter": emitter}},
    )

    assert [event["event_type"] for event in emitter.events] == [
        AgentEventType.PHASE_CHANGED,
        AgentEventType.CONTEXT_COMPACTING,
    ]
    assert result["phase"] == "context_compacting"
    assert result["last_context_strategy"] == "skip"
    # skip 策略不改消息，result 中不应有 messages key
    assert "messages" not in result

    payload = emitter.events[1]["payload"]
    assert payload["strategy"] == "skip"
    assert payload["reason"] == "below_watermark"


@pytest.mark.asyncio
async def test_context_compact_node_soft_prune() -> None:
    """Token 超过 40% 但有超长 ToolMessage 时，触发 soft-prune"""
    emitter = RecordingEmitter()
    # 创建超长 tool result（~5500 tokens 估算），max=10000 即 40%=4000, 60%=6000
    # 控制 content 长度使其落在 40%-60% 区间
    large_content = "x" * 22000
    messages = [
        HumanMessage(content="hello", id="msg-0"),
        AIMessage(content="ok", id="msg-1"),
        ToolMessage(
            content=large_content,
            tool_call_id="call-1",
            name="file_read",
            id="msg-2",
        ),
    ]

    result = await context_compact_node(
        make_state(
            messages=messages, phase="thinking", current_turn=4,
            max_context_tokens=10_000,
        ),
        {"configurable": {"event_emitter": emitter}},
    )

    assert result["phase"] == "context_compacting"
    assert result["last_context_strategy"] == "soft_prune"

    payload = emitter.events[1]["payload"]
    assert payload["strategy"] == "soft_prune"
    assert payload["prunedToolResults"] >= 1

    # tool 结果被裁剪
    pruned_msgs = result["messages"]
    tool_msg = pruned_msgs[2]
    content = tool_msg.content if hasattr(tool_msg, "content") else tool_msg.get("content", "")
    assert "soft-pruned" in content
    assert len(content) < len(large_content)
    # tool_call_id 保留
    assert getattr(tool_msg, "tool_call_id", "") == "call-1"


@pytest.mark.asyncio
async def test_context_compact_node_micro_compact() -> None:
    """Token 超过 60% 水线时，触发 micro-compact（摘要 + RemoveMessage）"""
    emitter = RecordingEmitter()
    # 创建足够多的消息让 token 超过 60%: max=20_000, 60%=12_000
    # 每个消息 ~250 tokens 估算, 100条 ≈ 25000 tokens > 12000
    messages = [SystemMessage(content="system", id="msg-sys")]
    for i in range(100):
        messages.append(
            AIMessage(
                content=f"message number {i} " + "x" * 1000,
                id=f"msg-{i}",
            )
        )

    result = await context_compact_node(
        make_state(
            messages=messages, phase="thinking", current_turn=4,
            max_context_tokens=20_000,
        ),
        {"configurable": {"event_emitter": emitter}},
    )

    assert result["phase"] == "context_compacting"
    assert result["last_context_strategy"] == "micro_compact"

    payload = emitter.events[1]["payload"]
    assert payload["strategy"] == "micro_compact"
    assert payload["reason"] == "watermark_60"
    # baseline 在 compact 后失效
    assert result["context_token_baseline"] is None


@pytest.mark.asyncio
async def test_context_compact_node_emergency_compact() -> None:
    """emergency_compact_requested=True 时，保留最近 3 条消息"""
    emitter = RecordingEmitter()
    messages = [SystemMessage(content="system", id="msg-sys")]
    for i in range(20):
        messages.append(
            AIMessage(content=f"msg-{i}", id=f"msg-id-{i}")
        )

    result = await context_compact_node(
        make_state(
            messages=messages, phase="thinking", current_turn=5,
            max_context_tokens=128_000,
            emergency_compact_requested=True,
        ),
        {"configurable": {"event_emitter": emitter}},
    )

    assert result["phase"] == "context_compacting"
    assert result["last_context_strategy"] == "emergency_compact"
    assert result["emergency_compact_requested"] is False
    assert result["context_compaction_attempts"] == 1

    payload = emitter.events[1]["payload"]
    assert payload["strategy"] == "emergency_compact"
    assert payload["reason"] == "context_overflow"
