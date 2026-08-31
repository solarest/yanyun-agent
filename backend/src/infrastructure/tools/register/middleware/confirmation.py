"""执行前确认中间件（task 4.2）。

对 `shell` 工具调用做危险命令分类；命中且未经会话级 allow-all 放行时，
发射 `tool:confirmation_required` SSE 事件、登记待审批调用，并返回
`ToolResult(metadata={"confirmation_required": True})` ——不阻塞等待。

tool_execute_node 收到此标记后将待确认调用写入 AgentState；用户决策
到达后由运行器从本地快照恢复，并以 bypass 标记跳过确认直接执行。
"""

from __future__ import annotations

from typing import Any, Optional

from src.domain.entities.event_types import AgentEventType
from src.domain.entities.tool import RegisteredTool, ToolContext, ToolResult
from src.infrastructure.tools.confirmation.classifier import CommandClassifier
from src.infrastructure.tools.confirmation.contract import (
    BYPASS_CONFIRMATION_KEY,
    CONFIRMATION_METADATA_KEY,
    CONFIRMATION_OPTIONS,
    ConfirmationRequiredPayload,
)
from src.infrastructure.tools.confirmation.store import (
    PendingApprovalRegistry,
    SessionApprovalStore,
)


class ConfirmationMiddleware:
    """危险 shell 命令执行前确认闸门（非阻塞版）。"""

    def __init__(
        self,
        classifier: CommandClassifier,
        registry: PendingApprovalRegistry,
        session_store: SessionApprovalStore,
    ) -> None:
        self._classifier = classifier
        self._registry = registry
        self._session_store = session_store

    async def process(
        self,
        tool: RegisteredTool,
        input: dict[str, Any],
        context: Optional[ToolContext],
        next_handler: Any,
    ) -> ToolResult:
        if tool.name != "shell":
            return await next_handler(tool, input, context)

        command = str(input.get("command", ""))

        # 快照恢复执行时携带 bypass 标记 → 跳过确认，直接执行
        extra = context.extra if context else {}
        if extra.get(BYPASS_CONFIRMATION_KEY):
            # allow_all 决策由 tool_execute_node 在快照恢复后
            # 调用 session_store.allow() 完成，此处只管放行
            return await next_handler(tool, input, context)

        classification = self._classifier.classify(command)
        if not classification.needs_confirmation:
            return await next_handler(tool, input, context)

        session_id = extra.get("parent_session_id") or extra.get("session_id") or ""
        if session_id and await self._session_store.is_allowed(
            session_id, classification.category
        ):
            return await next_handler(tool, input, context)

        effective_task_id = extra.get("parent_task_id") or (
            context.task_id if context else ""
        )
        tool_call_id = str(extra.get("tool_call_id", ""))
        emitter = extra.get("event_emitter")

        payload: ConfirmationRequiredPayload = {
            "toolCallId": tool_call_id,
            "command": command,
            "riskReason": classification.risk_reason,
            "workingDir": str(
                input.get("working_dir")
                or (context.workspace if context else "")
                or ""
            ),
            "options": list(CONFIRMATION_OPTIONS),
        }

        # 登记待审批（供 /approvals 端点校验存在性）
        await self._registry.register(effective_task_id, tool_call_id)

        # 发射 SSE 事件通知前端展示确认卡片
        if emitter is not None:
            await emitter.emit(
                effective_task_id,
                AgentEventType.TOOL_CONFIRMATION_REQUIRED,
                payload,
            )

        # 返回非阻塞标记——tool_execute_node 将其写为待确认状态
        return ToolResult(
            output=f"⚠️ 需要确认执行: {command}",
            success=False,
            error="confirmation_required",
            metadata={
                CONFIRMATION_METADATA_KEY: True,
                "tool_call_id": tool_call_id,
                "command": command,
                "category": classification.category,
                "risk_reason": classification.risk_reason,
                "session_id": session_id,
            },
        )
