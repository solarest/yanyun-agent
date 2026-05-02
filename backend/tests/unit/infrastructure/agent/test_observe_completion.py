"""测试 observe 节点对 LLM 完成声明的质量评估"""

import pytest
from unittest.mock import AsyncMock
from langchain_core.messages import AIMessage

from src.infrastructure.agent.nodes.observe_node import observe_node


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


def make_state(**overrides):
    state = {
        "messages": [],
        "task_id": "task-1",
        "workspace": "/tmp",
        "user_message": "hello",
        "task_start_message_count": 0,
        "current_turn": 1,
        "max_turns": 5,
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
        "system_prompt": "",
        "final_result": None,
        "error": None,
    }
    state.update(overrides)
    return state


@pytest.mark.asyncio
async def test_evaluate_completion_valid() -> None:
    """测试：有效的完成声明（包含实质性内容）"""
    emitter = RecordingEmitter()

    result = await observe_node(
        make_state(
            messages=[
                AIMessage(
                    content="任务已完成。我已创建了所有必要的文件，并进行了分析。"
                )
            ],
            last_executed_tool_call_ids=[],  # 无工具执行
        ),
        {"configurable": {"event_emitter": emitter}},
    )

    # 应该通过验证，路由到 finalize
    assert result["route_hint"] == "finalize"
    assert result["is_complete"] is True
    assert result["observation_quality"] == "complete"
    assert "final_result" in result


@pytest.mark.asyncio
async def test_evaluate_completion_too_short() -> None:
    """测试：完成声明过短"""
    emitter = RecordingEmitter()

    result = await observe_node(
        make_state(
            messages=[AIMessage(content="已完成")],  # 只有 3 个字符
            last_executed_tool_call_ids=[],
        ),
        {"configurable": {"event_emitter": emitter}},
    )

    # 应该拒绝，回到 llm_call
    assert result["route_hint"] == "llm_call"
    assert result["observation_quality"] == "incomplete"


@pytest.mark.asyncio
async def test_evaluate_completion_no_substance() -> None:
    """测试：完成声明缺少实质性内容"""
    emitter = RecordingEmitter()

    result = await observe_node(
        make_state(
            messages=[
                AIMessage(
                    content="任务完成，所有步骤已完成，工作已完成"
                )  # 只有完成关键词，没有实际内容
            ],
            last_executed_tool_call_ids=[],
        ),
        {"configurable": {"event_emitter": emitter}},
    )

    # 应该拒绝，回到 llm_call
    assert result["route_hint"] == "llm_call"
    assert result["observation_quality"] == "incomplete"


@pytest.mark.asyncio
async def test_evaluate_completion_not_claimed() -> None:
    """测试：未声明完成"""
    emitter = RecordingEmitter()

    result = await observe_node(
        make_state(
            messages=[AIMessage(content="这是一个普通的文本输出")],
            last_executed_tool_call_ids=[],
        ),
        {"configurable": {"event_emitter": emitter}},
    )

    # 应该回到 llm_call
    assert result["route_hint"] == "llm_call"


@pytest.mark.asyncio
async def test_evaluate_completion_with_english() -> None:
    """测试：英文完成声明"""
    emitter = RecordingEmitter()

    result = await observe_node(
        make_state(
            messages=[
                AIMessage(
                    content="Task complete. I have created all the files and analyzed the results."
                )
            ],
            last_executed_tool_call_ids=[],
        ),
        {"configurable": {"event_emitter": emitter}},
    )

    # 应该通过验证
    assert result["route_hint"] == "finalize"
    assert result["is_complete"] is True
