from src.application.use_cases.agent_workflow import (
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
        "awaiting_approval": False,
        "approval_request": None,
        "approved_tool_call_ids": [],
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
    }
    state.update(overrides)
    return state


def test_route_after_llm_plain_text_goes_to_stuck_detect() -> None:
    state = make_state(messages=[{"role": "assistant", "content": "Here is the answer."}])
    assert route_after_llm(state) == "stuck_detect"


def test_route_after_llm_blocks_tool_followup_when_turn_budget_exhausted() -> None:
    state = make_state(
        current_turn=3,
        max_turns=3,
        messages=[
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": "call-1", "name": "search", "args": {"q": "x"}}],
            }
        ],
    )

    # 超限时路由到 terminate 节点（由该节点设置 error/should_end）
    assert route_after_llm(state) == "terminate"


def test_route_after_tool_execute_ends_when_awaiting_user_input() -> None:
    state = make_state(awaiting_user_input=True)
    assert route_after_tool_execute(state) == "__end__"


def test_route_after_tool_execute_ends_when_awaiting_approval() -> None:
    state = make_state(awaiting_approval=True)
    assert route_after_tool_execute(state) == "__end__"
