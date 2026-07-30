"""ConfirmationMiddleware 单元测试（非阻塞版）。

中间件不再阻塞等待——检测到危险命令后立即返回 confirmation_required
元数据，由 tool_execute_node 调用 interrupt() 暂停图。
"""

import pytest

from src.domain.entities.event_types import AgentEventType
from src.domain.entities.tool import RegisteredTool, ToolContext, ToolResult
from src.infrastructure.tools.confirmation.classifier import CommandClassifier
from src.infrastructure.tools.confirmation.config import load_dangerous_commands
from src.infrastructure.tools.confirmation.contract import (
    BYPASS_CONFIRMATION_KEY,
    CONFIRMATION_METADATA_KEY,
    CONFIRMATION_OPTIONS,
)
from src.infrastructure.tools.confirmation.store import (
    PendingApprovalRegistry,
    SessionApprovalStore,
)
from src.infrastructure.tools.register.middleware.confirmation import (
    ConfirmationMiddleware,
)


def _shell_tool() -> RegisteredTool:
    async def func(input, context=None):  # noqa: ANN001
        return ToolResult(output="ran")

    return RegisteredTool(name="shell", description="", func=func)


class _RecordingEmitter:
    """记录发射的事件，不做决策投递（中间件不再阻塞等待 Future）。"""

    def __init__(self):
        self.events: list = []

    async def emit(self, task_id, event_type, payload):  # noqa: ANN001
        self.events.append((task_id, event_type, payload))


def _ctx(task_id, tool_call_id, emitter, session_id="sess-1") -> ToolContext:
    return ToolContext(
        task_id=task_id,
        extra={
            "tool_call_id": tool_call_id,
            "session_id": session_id,
            "event_emitter": emitter,
        },
    )


def _mw(registry, store) -> ConfirmationMiddleware:
    return ConfirmationMiddleware(
        CommandClassifier(load_dangerous_commands()),
        registry,
        store,
    )


class TestConfirmationMiddleware:
    @pytest.mark.asyncio
    async def test_safe_command_passthrough(self) -> None:
        """安全命令直接放行，无事件发射。"""
        reg, store = PendingApprovalRegistry(), SessionApprovalStore()
        emitter = _RecordingEmitter()
        mw = _mw(reg, store)
        called: list = []

        async def nh(tool, input, context):  # noqa: ANN001
            called.append(tool.name)
            return ToolResult(output="ok", success=True)

        r = await mw.process(_shell_tool(), {"command": "ls -la"}, _ctx("t", "c1", emitter), nh)
        assert r.success is True
        assert called == ["shell"]
        assert emitter.events == []

    @pytest.mark.asyncio
    async def test_dangerous_returns_confirmation_required_no_blocking(self) -> None:
        """危险命令：立即返回 confirmation_required 元数据 + 发射 SSE，不阻塞。"""
        reg, store = PendingApprovalRegistry(), SessionApprovalStore()
        emitter = _RecordingEmitter()
        mw = _mw(reg, store)
        called: list = []

        async def nh(tool, input, context):  # noqa: ANN001
            called.append("should_not_be_called")
            return ToolResult(output="ok", success=True)

        r = await mw.process(
            _shell_tool(), {"command": "rm -rf build"}, _ctx("t", "c1", emitter), nh
        )
        # 返回 confirmation_required 标记，next_handler 未被调用
        assert r.success is False
        assert r.error == "confirmation_required"
        assert r.metadata.get(CONFIRMATION_METADATA_KEY) is True
        assert r.metadata["command"] == "rm -rf build"
        assert r.metadata["category"] == "rm-recursive"
        assert called == []  # next_handler 未被调用

        # SSE 事件已发射
        assert len(emitter.events) == 1
        task_id, event_type, payload = emitter.events[0]
        assert task_id == "t"
        assert event_type == AgentEventType.TOOL_CONFIRMATION_REQUIRED
        assert payload["toolCallId"] == "c1"
        assert payload["command"] == "rm -rf build"
        assert payload["riskReason"]
        assert payload["options"] == list(CONFIRMATION_OPTIONS)

        # 已登记待审批
        assert await reg.has("t", "c1") is True

    @pytest.mark.asyncio
    async def test_dangerous_with_bypass_flag_passthrough(self) -> None:
        """携带 bypass_confirmation 标记 → 跳过确认，直接执行。"""
        reg, store = PendingApprovalRegistry(), SessionApprovalStore()
        emitter = _RecordingEmitter()
        mw = _mw(reg, store)
        called: list = []

        async def nh(tool, input, context):  # noqa: ANN001
            called.append(input.get("command"))
            return ToolResult(output="ok", success=True)

        ctx = ToolContext(
            task_id="t",
            extra={
                "tool_call_id": "c1",
                "session_id": "sess-1",
                "event_emitter": emitter,
                BYPASS_CONFIRMATION_KEY: True,
            },
        )
        r = await mw.process(_shell_tool(), {"command": "rm -rf build"}, ctx, nh)
        assert r.success is True
        assert called == ["rm -rf build"]
        assert emitter.events == []  # 无确认事件

    @pytest.mark.asyncio
    async def test_allow_all_session_whitelist_passthrough(self) -> None:
        """会话白名单已有该类别 → 直接放行，不再发射确认事件。"""
        reg, store = PendingApprovalRegistry(), SessionApprovalStore()
        await store.allow("sess-1", "sudo")
        emitter = _RecordingEmitter()
        mw = _mw(reg, store)
        called: list = []

        async def nh(tool, input, context):  # noqa: ANN001
            called.append(input.get("command"))
            return ToolResult(output="ok", success=True)

        r = await mw.process(
            _shell_tool(), {"command": "sudo apt update"}, _ctx("t", "c1", emitter), nh
        )
        assert r.success is True
        assert called == ["sudo apt update"]
        assert emitter.events == []

    @pytest.mark.asyncio
    async def test_non_shell_tool_passthrough(self) -> None:
        """非 shell 工具：无论什么命令都直接放行。"""
        reg, store = PendingApprovalRegistry(), SessionApprovalStore()
        emitter = _RecordingEmitter()
        mw = _mw(reg, store)
        called: list = []

        async def nh(tool, input, context):  # noqa: ANN001
            called.append(tool.name)
            return ToolResult(output="ok", success=True)

        read_tool = RegisteredTool(name="file_read", description="", func=lambda i, c: ToolResult(output="ok"))
        r = await mw.process(read_tool, {"path": "/etc/passwd"}, _ctx("t", "c1", emitter), nh)
        assert r.success is True
        assert called == ["file_read"]
        assert emitter.events == []

    @pytest.mark.asyncio
    async def test_registry_has_and_remove(self) -> None:
        """PendingApprovalRegistry.has / remove 行为正确。"""
        reg = PendingApprovalRegistry()
        assert await reg.has("t1", "c1") is False

        await reg.register("t1", "c1")
        assert await reg.has("t1", "c1") is True
        assert await reg.has("t1", "c2") is False

        await reg.remove("t1", "c1")
        assert await reg.has("t1", "c1") is False
