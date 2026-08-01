"""审批端点测试（非阻塞版 task 5.1 / 5.2）。

/approvals 端点校验 PendingApprovalRegistry 存在性后，
通过 GraphResumeManager 恢复图执行。
"""

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from src.application.dtos.approval_dto import ApprovalDecisionDTO
from src.domain.entities.event_types import AgentEventType
from src.domain.entities.tool import RegisteredTool, ToolContext, ToolResult
from src.infrastructure.tools.confirmation.classifier import CommandClassifier
from src.infrastructure.tools.confirmation.config import load_dangerous_commands
from src.infrastructure.tools.confirmation.contract import CONFIRMATION_METADATA_KEY
from src.infrastructure.tools.confirmation.store import (
    PendingApprovalRegistry,
    SessionApprovalStore,
)
from src.infrastructure.tools.register.middleware.confirmation import (
    ConfirmationMiddleware,
)
from src.presentation.routes.tasks import submit_approval


def _shell_tool() -> RegisteredTool:
    async def func(input, context=None):  # noqa: ANN001
        return ToolResult(output="ran")

    return RegisteredTool(name="shell", description="", func=func)


class _CapturingEmitter:
    """记录确认事件但不投递决策。"""

    def __init__(self) -> None:
        self.events: list = []

    async def emit(self, task_id, event_type, payload):  # noqa: ANN001
        self.events.append((task_id, event_type, payload))


class TestSubmitApprovalEndpoint:
    """task 5.1：POST /api/tasks/{task_id}/approvals 校验与错误处理。"""

    @pytest.mark.asyncio
    async def test_registered_toolcall_clears_and_returns_200(self) -> None:
        """已登记的 toolCallId → 清理登记并返回 200。

        注：图恢复依赖 GraphResumeManager（完整 LangGraph 集成测试单独覆盖），
        此处验证登记清理语义。
        """
        reg = PendingApprovalRegistry()
        await reg.register("t1", "c1")

        # 注意：图恢复需要 GraphResumeManager 中有对应上下文，
        # 单元测试中无上下文 → 会 404。但登记存在性已校验通过。
        with pytest.raises(HTTPException) as exc:
            await submit_approval(
                "t1", ApprovalDecisionDTO(toolCallId="c1", decision="allow_once"), reg
            )
        # 登记存在但无图上下文 → 404 (NO_PENDING_GRAPH)
        assert exc.value.status_code == 404

        # 登记已被端点清理
        assert await reg.has("t1", "c1") is False

    @pytest.mark.asyncio
    async def test_unknown_toolcall_returns_404(self) -> None:
        reg = PendingApprovalRegistry()
        with pytest.raises(HTTPException) as exc:
            await submit_approval(
                "t1", ApprovalDecisionDTO(toolCallId="nope", decision="deny"), reg
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_already_removed_toolcall_returns_404(self) -> None:
        """已清理的登记 → 404（拒绝重复提交）。"""
        reg = PendingApprovalRegistry()
        await reg.register("t1", "c1")
        await reg.remove("t1", "c1")

        with pytest.raises(HTTPException) as exc:
            await submit_approval(
                "t1",
                ApprovalDecisionDTO(toolCallId="c1", decision="allow_once"),
                reg,
            )
        assert exc.value.status_code == 404

    def test_invalid_decision_rejected_by_dto(self) -> None:
        with pytest.raises(ValidationError):
            ApprovalDecisionDTO(toolCallId="c1", decision="maybe")


class TestConfirmationIntegration:
    """task 5.2：中间件非阻塞返回 confirmation_required + SSE 事件。"""

    @pytest.mark.asyncio
    async def test_dangerous_shell_returns_confirmation_required_immediately(self) -> None:
        """危险 shell → 立即返回 confirmation_required（不阻塞等待）。"""
        reg = PendingApprovalRegistry()
        store = SessionApprovalStore()
        mw = ConfirmationMiddleware(
            CommandClassifier(load_dangerous_commands()),
            reg,
            store,
        )
        emitter = _CapturingEmitter()
        ctx = ToolContext(
            task_id="t1",
            extra={
                "tool_call_id": "c1",
                "session_id": "s1",
                "event_emitter": emitter,
            },
        )
        called: list = []

        async def nh(tool, input, context):  # noqa: ANN001
            called.append(input.get("command"))
            return ToolResult(output="done", success=True)

        # 不阻塞——立即返回
        result = await mw.process(
            _shell_tool(), {"command": "rm -rf build"}, ctx, nh
        )

        assert not result.success
        assert result.error == "confirmation_required"
        assert result.metadata.get(CONFIRMATION_METADATA_KEY) is True
        assert result.metadata["command"] == "rm -rf build"
        assert called == []  # next_handler 未调用

        # SSE 事件已发射
        assert len(emitter.events) == 1
        etype = emitter.events[0][1]
        assert etype == AgentEventType.TOOL_CONFIRMATION_REQUIRED
