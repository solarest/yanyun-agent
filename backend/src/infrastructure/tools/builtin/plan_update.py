"""基础设施层 - Plan更新工具

子Agent通过此工具向主Agent报告plan步骤的完成状态。
"""

import logging
from typing import Optional

from src.domain.entities.tool import ToolContext, ToolResult
from src.infrastructure.tools.decorator import tool

logger = logging.getLogger(__name__)


@tool(
    name="plan_update",
    description="向主Agent报告当前plan步骤的完成状态。仅子Agent使用。",
    category="plan",
    returns="更新确认",
    timeout_ms=3000,
)
async def plan_update(
    step_id: int,
    status: str,
    result: str,
    context: Optional[ToolContext] = None,
) -> ToolResult:
    """更新plan步骤状态
    
    Args:
        step_id: 步骤ID
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
        output=f"Step {step_id} marked as {status}. Result recorded.",
        metadata={
            "type": "plan_update",
            "step_id": step_id,
            "status": status,
            "result": result,
            "awaiting_user_input": False,
        },
    )
