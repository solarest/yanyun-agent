"""基础设施层 - 任务更新工具

更新已创建任务的执行状态和结果。
"""

import logging
from typing import Optional

from src.domain.tool import ToolContext, ToolResult
from src.infrastructure.tools.decorator import tool

logger = logging.getLogger(__name__)


@tool(
    name="task_update",
    description="更新任务的完成状态。在子任务执行完成后调用此工具记录结果。",
    category="task",
    returns="更新确认",
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
        task_id: 任务ID
        status: 完成状态 (completed | failed)
        result: 执行结果摘要
    """
    if status not in ("completed", "failed"):
        return ToolResult(
            output="Error: status must be 'completed' or 'failed'",
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
