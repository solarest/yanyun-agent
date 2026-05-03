from src.application.use_cases.agent_workflow import (
    route_after_llm,
    route_after_tool_execute,
    route_after_loop_detect,
    route_after_stuck_detect,
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
        "loop_detection_count": 0,
        "loop_detected": False,
        "loop_type": None,
        "stuck_detection_count": 0,
        "stuck_detected": False,
        "stuck_type": None,
        "current_llm_text": "",
        "empty_retry_count": 0,
        "planning_retry_count": 0,
        "system_prompt": "",
        "final_result": None,
        "error": None,
        "observation_summary": None,
        "observation_quality": None,
        "observation_items": [],
        "consecutive_empty_observations": 0,
        "last_error_category": None,
        "compression_strategy": None,
        "is_sub_agent": False,
        "parent_task_id": None,
    }
    state.update(overrides)
    return state


# === route_after_llm 测试 ===


def test_route_after_llm_plain_text_goes_to_stuck_detect() -> None:
    """纯文本响应路由到 stuck_detect(文本评估+卡住检测)"""
    state = make_state(
        messages=[{"role": "assistant", "content": "Here is the answer."}])
    assert route_after_llm(state) == "stuck_detect"


def test_route_after_llm_tool_calls_goes_to_loop_detect() -> None:
    """有 tool_calls 路由到 loop_detect(前置守卫)"""
    state = make_state(
        messages=[
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "call-1", "name": "search", "args": {"q": "x"}}],
            }
        ],
    )
    assert route_after_llm(state) == "loop_detect"


def test_route_after_llm_should_end() -> None:
    """should_end=True 时路由到 END"""
    state = make_state(should_end=True, messages=[
                       {"role": "assistant", "content": "done"}])
    assert route_after_llm(state) == "__end__"


def test_route_after_llm_empty_messages() -> None:
    """消息为空时路由到 END"""
    state = make_state(messages=[])
    assert route_after_llm(state) == "__end__"


# === route_after_loop_detect 测试 ===


def test_route_after_loop_detect_no_loop() -> None:
    """未检测到循环时路由到 tool_execute"""
    state = make_state(loop_detected=False)
    assert route_after_loop_detect(state) == "tool_execute"


def test_route_after_loop_detect_should_end() -> None:
    """检测到循环且 should_end=True 时路由到 END"""
    state = make_state(loop_detected=True, should_end=True,
                       loop_detection_count=3)
    assert route_after_loop_detect(state) == "__end__"


def test_route_after_loop_detect_count_2() -> None:
    """loop_detection_count=2 时路由到 context_compact"""
    state = make_state(loop_detected=True, loop_detection_count=2)
    assert route_after_loop_detect(state) == "context_compact"


def test_route_after_loop_detect_count_1() -> None:
    """loop_detection_count=1 时路由回 llm_call(已注入反馈)"""
    state = make_state(loop_detected=True, loop_detection_count=1)
    assert route_after_loop_detect(state) == "llm_call"


# === route_after_tool_execute 测试 ===


def test_route_after_tool_execute_awaiting_user() -> None:
    """awaiting_user_input=True 时路由到 END"""
    state = make_state(awaiting_user_input=True)
    assert route_after_tool_execute(state) == "__end__"


def test_route_after_tool_execute_goes_to_loop_detect() -> None:
    """工具执行后路由到 loop_detect(循环检测前置守卫)"""
    state = make_state(awaiting_user_input=False)
    assert route_after_tool_execute(state) == "loop_detect"


# === route_after_stuck_detect 测试 ===


def test_route_after_stuck_detect_should_end() -> None:
    """should_end=True 时路由到 END"""
    state = make_state(should_end=True, stuck_detection_count=3)
    assert route_after_stuck_detect(state) == "__end__"


def test_route_after_stuck_detect_goes_to_llm_call() -> None:
    """未终止时路由回 llm_call(已注入反馈)"""
    state = make_state(should_end=False, stuck_detection_count=1)
    assert route_after_stuck_detect(state) == "llm_call"
