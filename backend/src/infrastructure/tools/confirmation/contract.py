"""确认事件契约（task 2.2）。

定义 `tool:confirmation_required` 事件的负载形状与用户决策的合法取值，
供 ConfirmationMiddleware 构造、/approvals 端点校验、前端镜像共同引用。

`taskId` 不在本契约内——由 `SSEEventDTO.create` 按 emit 时的 `task_id`
自动盖戳（见 `event_dto.py`），故中间件只需在 `effective_task_id` 上 emit。
"""

from __future__ import annotations

from typing import Literal, TypedDict

ApprovalDecision = Literal["allow_once", "allow_all", "deny"]
"""用户在确认卡上可选的三种决策。"""

CONFIRMATION_OPTIONS: tuple[str, ...] = ("allow_once", "allow_all", "deny")
"""事件负载 `options` 字段的取值集合。"""

# ── 确认状态 元数据键 ───────────────────────────────────────────
# ConfirmationMiddleware → ToolResult.metadata 中标记"需确认"的键；
# tool_execute_node 据此创建可持久化的 pending_confirmation 状态。
CONFIRMATION_METADATA_KEY: str = "confirmation_required"

# ToolContext.extra 中标记"跳过确认"的键；
# tool_execute_node 从快照恢复后重执行时设置，ConfirmationMiddleware 据此放行。
BYPASS_CONFIRMATION_KEY: str = "bypass_confirmation"


class ConfirmationRequiredPayload(TypedDict):
    """`tool:confirmation_required` 事件负载。"""

    toolCallId: str
    command: str
    riskReason: str
    workingDir: str
    options: list[str]
