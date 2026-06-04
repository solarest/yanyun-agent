"""基础设施层 - 任务更新工具

更新已创建任务的执行状态和结果。
"""

import logging
from typing import Optional

from src.domain.entities.tool import ToolContext, ToolResult
from src.infrastructure.tools.decorator import tool

logger = logging.getLogger(__name__)


@tool(
    name="task_update",
    description=(
        "Update a task's status created by task_create. "
        "Use in_progress to mark a task as started (set result to a brief progress note). "
        "Use completed or failed when the task finishes (set result to the final outcome or error reason)."
    ),
    category="task",
    returns="Update confirmation",
    timeout_ms=3000,
)
async def task_update(
    task_id: int,
    status: str,
    result: str,
    context: Optional[ToolContext] = None,
) -> ToolResult:
    """更新任务状态

    Args:
        task_id: 任务ID（由 task_create 返回的 ID）
        status: 任务状态 — "in_progress" (开始执行), "completed" (已完成), "failed" (执行失败)
        result: in_progress 时为进展简述，completed 时为最终结果，failed 时为失败原因
    """
    VALID_STATUSES = ("in_progress", "completed", "failed")
    if status not in VALID_STATUSES:
        return ToolResult(
            output=f"Error: status must be one of: {', '.join(VALID_STATUSES)}",
            success=False,
            error="invalid_input",
        )

    if not result.strip():
        return ToolResult(
            output="Error: result cannot be empty",
            success=False,
            error="invalid_input",
        )

    # 验证context
    if not context or not context.task_id:
        return ToolResult(
            output="Error: invalid context",
            success=False,
            error="invalid_context",
        )

    # 注意: 实际的事件发射将在tool_execute_node中通过metadata传递
    # 这里只返回确认信息
    return ToolResult(
        output=f"Task {task_id} marked as {status}. Result recorded.",
        metadata={
            "type": "task_update",
            "task_id": task_id,
            "status": status,
            "result": result,
            "awaiting_user_input": False,
        },
    )
