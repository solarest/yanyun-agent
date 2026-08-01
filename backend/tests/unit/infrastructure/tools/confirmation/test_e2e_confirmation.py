"""确认流集成测试（非阻塞版）。

验证中间件 pipeline + /approvals 端点协同：
- 危险命令触发 confirmation_required + SSE 事件 + 登记
- /approvals 端点校验存在性、清理登记
- 会话白名单跨调用生效

完整的 interrupt/resume 图执行测试需要 LangGraph + checkpointer
集成环境，不在本文件中覆盖。
"""

import pytest
from fastapi import HTTPException

from src.application.dtos.approval_dto import ApprovalDecisionDTO
from src.domain.entities.event_types import AgentEventType
from src.domain.entities.tool import RegisteredTool, ToolContext, ToolResult
from src.domain.value_objects.tool_policy import ToolPolicy
from src.infrastructure.tools.confirmation.contract import CONFIRMATION_METADATA_KEY
from src.infrastructure.tools.confirmation.pipeline import build_default_pipeline
from src.infrastructure.tools.confirmation.store import (
    get_default_registry,
    get_default_session_store,
)
from src.infrastructure.tools.register.registry import ToolRegistry
from src.presentation.routes.tasks import submit_approval


def _fake_shell() -> RegisteredTool:
    """假 shell 工具——不依赖全局注册表，避免跨测试状态污染。"""

    async def fn(input, context=None):  # noqa: ANN001
        return ToolResult(output="ran", success=True)

    return RegisteredTool(
        name="shell",
        description="",
        func=fn,
        policy=ToolPolicy(),
    )


def _reg() -> ToolRegistry:
    """创建含确认管道的 ToolRegistry（独立实例）。"""
    reg = ToolRegistry(pipeline=build_default_pipeline())
    reg.register(_fake_shell())
    return reg


class _CapturingEmitter:
    def __init__(self) -> None:
        self.events: list = []

    async def emit(self, task_id, event_type, payload):  # noqa: ANN001
        self.events.append((task_id, event_type, payload))


def _ctx(task_id: str, tool_call_id: str, emitter, session_id: str) -> ToolContext:
    return ToolContext(
        task_id=task_id,
        extra={
            "tool_call_id": tool_call_id,
            "session_id": session_id,
            "event_emitter": emitter,
        },
    )


@pytest.mark.asyncio
async def test_dangerous_triggers_confirmation_required_and_registers() -> None:
    """危险命令 → 立即返回 confirmation_required + SSE + 登记。"""
    reg = _reg()
    emitter = _CapturingEmitter()
    ctx = _ctx("e2e-1", "call-1", emitter, "e2e-sess-a")

    result = await reg.execute(
        "shell", {"command": 'echo hi > /tmp/test.txt'}, ctx
    )

    # 返回 confirmation_required 标记（非阻塞）
    assert not result.success
    assert result.error == "confirmation_required"
    assert result.metadata.get(CONFIRMATION_METADATA_KEY) is True
    assert "echo hi" in result.metadata["command"]

    # SSE 事件已发射
    assert len(emitter.events) == 1
    assert emitter.events[0][1] == AgentEventType.TOOL_CONFIRMATION_REQUIRED

    # 已登记
    shared = get_default_registry()
    assert await shared.has("e2e-1", "call-1") is True


@pytest.mark.asyncio
async def test_approval_endpoint_validates_registry_existence() -> None:
    """/approvals 端点校验待审批调用存在性 → 不存在则 404。"""
    shared = get_default_registry()
    # 先登记一个
    await shared.register("e2e-2", "call-2")
    assert await shared.has("e2e-2", "call-2") is True

    # 成功后登记应被清理
    await shared.remove("e2e-2", "call-2")
    assert await shared.has("e2e-2", "call-2") is False

    # 重复提交 → 404（已清理）
    with pytest.raises(HTTPException) as exc:
        await submit_approval(
            "e2e-2",
            ApprovalDecisionDTO(toolCallId="call-2", decision="allow_once"),
            shared,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_approval_nonexistent_returns_404() -> None:
    """从未登记的 toolCallId → 404。"""
    shared = get_default_registry()
    with pytest.raises(HTTPException) as exc:
        await submit_approval(
            "nonexistent-task",
            ApprovalDecisionDTO(toolCallId="nonexistent-call", decision="allow_once"),
            shared,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_session_whitelist_second_call_no_confirmation() -> None:
    """会话白名单：allow_all 后同类别命令不再触发确认（直接放行 + 无事件）。"""
    from src.infrastructure.tools.confirmation.store import get_default_session_store

    store = get_default_session_store()
    await store.allow("e2e-sess-whitelist", "redirect-overwrite")

    reg = _reg()
    emitter = _CapturingEmitter()
    ctx = _ctx("e2e-3", "call-3", emitter, "e2e-sess-whitelist")

    # echo hi > file 会命中 redirect-overwrite，但已在白名单中 → 直接执行
    result = await reg.execute(
        "shell", {"command": 'echo allowed > /tmp/test.txt'}, ctx
    )
    # fake shell 不真正执行命令，但管道已放行（success=True）
    assert result.success
    # 无确认事件（白名单直放）
    assert emitter.events == []


@pytest.mark.asyncio
async def test_safe_command_no_confirmation() -> None:
    """安全命令直接执行，不触发确认。"""
    reg = _reg()
    emitter = _CapturingEmitter()
    ctx = _ctx("e2e-4", "call-4", emitter, "e2e-sess-d")

    # echo + 重定向 → 命中 redirect-overwrite，触发确认
    await reg.execute("shell", {"command": "echo safe > /tmp/safe.txt"}, ctx)

    # ls 是安全命令 → 直接放行
    result2 = await reg.execute("shell", {"command": "ls -la"}, ctx)
    assert result2.success

    # 只有 echo 那次触发了确认事件
    confirm_events = [e for e in emitter.events if e[1] == AgentEventType.TOOL_CONFIRMATION_REQUIRED]
    assert len(confirm_events) == 1
