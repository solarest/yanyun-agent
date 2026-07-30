from src.domain.services.agent_routing import (
    route_after_llm,
    route_after_tool_execute,
)


def make_state(**overrides):
    state = {
        "messages": [],
        "task_id": "task-1",
        "workspace": "/tmp",
        "user_message": "hello",
        "task_start_message_count": 0,
        "current_turn": 1,
        "max_turns": 3,
        "phase": "thinking",
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
        # === Sub-Agent ===
        "is_sub_agent": False,
        "parent_task_id": None,
    }
    state.update(overrides)
    return state


# === route_after_llm 测试 ===


def test_route_after_llm_plain_text_goes_to_end() -> None:
    """纯文本响应直接终止(认为任务已完成)"""
    state = make_state(
        messages=[{"role": "assistant", "content": "Here is the answer."}])
    assert route_after_llm(state) == "__end__"


def test_route_after_llm_tool_calls_goes_to_tool_execute() -> None:
    """有 tool_calls 直接路由到 tool_execute (不再经过 loop_detect)"""
    state = make_state(
        messages=[
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "call-1", "name": "search", "args": {"q": "x"}}],
            }
        ],
    )
    assert route_after_llm(state) == "tool_execute"


def test_route_after_llm_should_end() -> None:
    """should_end=True 时路由到 END"""
    state = make_state(should_end=True, messages=[
                       {"role": "assistant", "content": "done"}])
    assert route_after_llm(state) == "__end__"


def test_route_after_llm_emergency_compact() -> None:
    """emergency_compact_requested=True 时路由到 context_compact（优先）"""
    state = make_state(emergency_compact_requested=True)
    assert route_after_llm(state) == "context_compact"


def test_route_after_llm_emergency_overrides_should_end() -> None:
    """emergency_compact_requested 优先于 should_end"""
    state = make_state(emergency_compact_requested=True, should_end=True)
    assert route_after_llm(state) == "context_compact"


# === route_after_tool_execute 测试 ===


def test_route_after_tool_execute_awaiting_user() -> None:
    """awaiting_user_input=True 时路由到 END"""
    state = make_state(awaiting_user_input=True)
    assert route_after_tool_execute(state) == "__end__"


def test_route_after_tool_execute_goes_to_context_compact() -> None:
    """有工具执行结果时路由到 context_compact（每轮 LLM 前置守门）"""
    state = make_state(
        awaiting_user_input=False,
        last_executed_tool_call_ids=["call-1", "call-2"],
    )
    assert route_after_tool_execute(state) == "context_compact"


def test_route_after_tool_execute_no_tools_goes_to_context_compact() -> None:
    """无工具执行结果时路由到 context_compact"""
    state = make_state(
        awaiting_user_input=False,
        last_executed_tool_call_ids=[],
    )
    assert route_after_tool_execute(state) == "context_compact"
