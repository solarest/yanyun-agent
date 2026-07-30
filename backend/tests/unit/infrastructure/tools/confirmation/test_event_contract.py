"""确认事件契约测试（task 2.1 / 2.2）"""

from src.application.agent_loop.event_dto import to_sse_event_name
from src.domain.entities.event_types import AgentEventType
from src.infrastructure.tools.confirmation.contract import (
    CONFIRMATION_OPTIONS,
    ConfirmationRequiredPayload,
)


def test_confirmation_required_event_type_defined() -> None:
    assert AgentEventType.TOOL_CONFIRMATION_REQUIRED.value == "tool:confirmation_required"


def test_confirmation_required_wire_name_normalized() -> None:
    # SSE 协议层仅把命名空间冒号替换为连字符、保留下划线（与
    # step:parallel_group_started -> step-parallel_group_started 一致）
    assert to_sse_event_name(AgentEventType.TOOL_CONFIRMATION_REQUIRED) == (
        "tool-confirmation_required"
    )


def test_confirmation_options_contract() -> None:
    assert CONFIRMATION_OPTIONS == ("allow_once", "allow_all", "deny")


def test_payload_shape_is_constructable() -> None:
    p: ConfirmationRequiredPayload = {
        "toolCallId": "call_1",
        "command": "rm -rf /",
        "riskReason": "递归删除",
        "workingDir": "/tmp",
        "options": list(CONFIRMATION_OPTIONS),
        # taskId 由 SSEEventDTO.create 按 emit 的 task_id 自动盖戳，不在本契约内
    }
    assert p["toolCallId"] == "call_1"
    assert p["options"] == ["allow_once", "allow_all", "deny"]
