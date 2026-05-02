"""Observe 节点单元测试

测试 observe_node 的核心功能：
1. 工具结果质量判定
2. 错误分类
3. 反思注入
4. 路由建议
5. 完成声明评估（新增）
"""

import pytest
from langchain_core.messages import HumanMessage

from src.infrastructure.agent.nodes.observe_node import observe_node


def _ok_result(tool_name: str, output: str, metadata: dict | None = None) -> dict:
    return {
        "tool_name": tool_name,
        "status": "success",
        "output": output,
        "metadata": metadata or {},
    }


def _err_result(tool_name: str, error: str, metadata: dict | None = None) -> dict:
    return {
        "tool_name": tool_name,
        "status": "error",
        "error": error,
        "metadata": metadata or {},
    }


def _state(**overrides) -> dict:
    state = {
        "messages": [],
        "task_id": "task-1",
        "workspace": "/tmp",
        "user_message": "hello",
        "task_start_message_count": 0,
        "current_turn": 1,
        "max_turns": 5,
        "phase": "tool_executing",
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
        "consecutive_empty_observations": 0,
    }
    state.update(overrides)
    return state


def _config(**overrides) -> dict:
    cfg = {"configurable": {}}
    if overrides:
        cfg["configurable"]["observe_options"] = overrides
    return cfg


class RecordingEmitter:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def emit(self, task_id: str, event_type: str, payload: dict) -> None:
        self.events.append(
            {"task_id": task_id, "event_type": event_type, "payload": payload}
        )

    async def emit_phase_changed(
        self, task_id: str, new_phase: str, previous_phase: str, turn: int
    ) -> None:
        await self.emit(
            task_id,
            "phase:changed",
            {"phase": new_phase, "previousPhase": previous_phase, "turn": turn},
        )


# === 场景 1: 单工具成功 → 无反思注入 ===


@pytest.mark.asyncio
async def test_single_good_result_no_reflection_injected() -> None:
    emitter = RecordingEmitter()
    state = _state(
        tool_results={"tc1": _ok_result("web_search", "useful content")},
        last_executed_tool_call_ids=["tc1"],
    )
    result = await observe_node(state, _config(emitter=emitter))

    assert result["observation_quality"] == "good"
    assert result["route_hint"] == "llm_call"
    # 单工具成功不注入反思
    assert "messages" not in result or not result["messages"]


# === 场景 2: 空结果 → 注入反思 ===


@pytest.mark.asyncio
async def test_empty_result_injects_reflection() -> None:
    state = _state(
        tool_results={"tc1": _ok_result("web_search", "")},
        last_executed_tool_call_ids=["tc1"],
    )
    result = await observe_node(state, _config())

    assert result["observation_quality"] == "empty"
    assert "messages" in result
    assert "empty" in result["messages"][0].content.lower()


# === 场景 3: 连续空观察 → 路由到 loop_detect ===


@pytest.mark.asyncio
async def test_consecutive_empty_triggers_loop_detect() -> None:
    state = _state(
        tool_results={"tc1": _ok_result("web_search", "")},
        last_executed_tool_call_ids=["tc1"],
        consecutive_empty_observations=1,  # 已经有 1 次
    )
    result = await observe_node(state, _config(max_consecutive_empty=2))

    assert result["observation_quality"] == "empty"
    assert result["consecutive_empty_observations"] == 2
    # 达到阈值，路由到 loop_detect
    assert result["route_hint"] == "loop_detect"


# === 场景 4: 错误分类 - timeout ===


@pytest.mark.asyncio
async def test_classify_timeout_error() -> None:
    state = _state(
        tool_results={"tc1": _err_result("shell", "command timed out")},
        last_executed_tool_call_ids=["tc1"],
    )
    result = await observe_node(state, _config())

    assert result["observation_quality"] == "failed"
    assert result["last_error_category"] == "timeout"


# === 场景 5: 致命错误 (permission) → 路由到 finalize ===


@pytest.mark.asyncio
async def test_permission_error_routes_to_finalize() -> None:
    state = _state(
        tool_results={"tc1": _err_result("file_write", "permission denied")},
        last_executed_tool_call_ids=["tc1"],
    )
    result = await observe_node(state, _config())

    assert result["observation_quality"] == "failed"
    assert result["last_error_category"] == "permission"
    # 致命错误，路由到 finalize
    assert result["route_hint"] == "finalize"


# === 场景 8: 多工具全部成功 → 注入轻量总结 ===


@pytest.mark.asyncio
async def test_multi_success_injects_summary() -> None:
    state = _state(
        tool_results={
            "tc1": _ok_result("web_search", "result A"),
            "tc2": _ok_result("read_file", "result B content"),
        },
        last_executed_tool_call_ids=["tc1", "tc2"],
    )
    result = await observe_node(state, _config())

    assert result["observation_quality"] == "good"
    assert "messages" in result
    assert "2 tools succeeded" in result["messages"][0].content


# === 场景 9: skipped 工具被忽略 ===


@pytest.mark.asyncio
async def test_skipped_tool_is_ignored() -> None:
    state = _state(
        tool_results={
            "tc_skip": {"tool_name": "plan", "status": "skipped", "output": None},
            "tc_ok": _ok_result("real_tool", "real output"),
        },
        last_executed_tool_call_ids=["tc_skip", "tc_ok"],
    )
    result = await observe_node(state, _config())

    # 只计入 tc_ok
    ids = [i["toolCallId"] for i in result["observation_items"]]
    assert ids == ["tc_ok"]


# === 场景 10: 反思注入关闭 ===


@pytest.mark.asyncio
async def test_reflection_inject_disabled() -> None:
    state = _state(
        tool_results={"tc1": _ok_result("web_search", "[]")},
        last_executed_tool_call_ids=["tc1"],
    )
    result = await observe_node(state, _config(enable_reflection_inject=False))

    assert result["observation_quality"] == "empty"
    # 关闭注入，不应有 messages
    assert "messages" not in result or not result["messages"]


# === 场景 11: metadata.error_type 优先 ===


@pytest.mark.asyncio
async def test_metadata_error_type_takes_precedence() -> None:
    state = _state(
        tool_results={
            "tc1": _err_result(
                "custom", "some message", metadata={"error_type": "business_error"}
            )
        },
        last_executed_tool_call_ids=["tc1"],
    )
    result = await observe_node(state, _config())

    assert result["last_error_category"] == "business_error"


# === 场景 12: 无 emitter 也能工作 ===


@pytest.mark.asyncio
async def test_works_without_emitter() -> None:
    state = _state(
        tool_results={"tc1": _ok_result("web_search", "content")},
        last_executed_tool_call_ids=["tc1"],
    )
    # 不注入 emitter
    result = await observe_node(state, {"configurable": {}})

    assert result["observation_quality"] == "good"
    assert result["route_hint"] == "llm_call"
