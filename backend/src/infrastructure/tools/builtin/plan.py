"""基础设施层 - 任务规划工具

将复杂任务分解为可执行的步骤计划。
"""

import logging
from typing import Any, Optional

from src.domain.entities.tool import ToolContext, ToolResult
from src.infrastructure.tools.decorator import tool

logger = logging.getLogger(__name__)


@tool(
    name="plan",
    description="将复杂任务分解为可执行的步骤计划。用于在执行前组织思路和明确行动路径。",
    category="plan",
    returns="结构化的任务计划",
    timeout_ms=5000,
)
async def plan(
    goal: str,
    steps: list[str],
    context: Optional[ToolContext] = None,
) -> ToolResult:
    """任务规划工具

    Args:
        goal: 任务目标描述
        steps: 执行步骤列表
    """
    if not goal.strip():
        return ToolResult(
            output="Error: goal cannot be empty",
            success=False,
            error="invalid_input",
        )

    if not steps:
        return ToolResult(
            output="Error: steps cannot be empty",
            success=False,
            error="invalid_input",
        )

    structured_steps = [
        {"id": i, "description": str(step)}
        for i, step in enumerate(steps, 1)
    ]
    execution_order = [step["id"] for step in structured_steps]

    output_parts = [f"## Plan: {goal}\n"]
    for step in structured_steps:
        output_parts.append(f"- [ ] Step {step['id']}: {step['description']}")

    return ToolResult(
        output="\n".join(output_parts),
        metadata={
            "type": "plan",
            "goal": goal,
            "execution_order": execution_order,
            "steps": structured_steps,
            "step_count": len(steps),
        },
    )


@tool(
    name="plan_execute",
    description="创建并执行结构化计划。支持串行+并行混合执行。execution_order格式: [1,[2,3,4],5] 表示1串行,[2,3,4]并行,5串行。",
    category="plan",
    returns="plan_id和plan结构确认,将触发plan执行流程",
    timeout_ms=5000,
)
async def plan_execute(
    goal: str,
    execution_order: list[Any],
    steps: list[dict[str, Any]],
    context: Optional[ToolContext] = None,
) -> ToolResult:
    """创建结构化执行计划
    
    Args:
        goal: 计划目标
        execution_order: 执行顺序列表,整数表示串行,列表表示并行。如 [1, [2,3,4], 5]
        steps: 步骤定义列表,每个步骤包含 {"id": int, "description": str}
    """
    if not goal.strip():
        return ToolResult(
            output="Error: goal cannot be empty",
            success=False,
            error="invalid_input",
        )
    
    if not execution_order:
        return ToolResult(
            output="Error: execution_order cannot be empty",
            success=False,
            error="invalid_input",
        )
    
    if not steps:
        return ToolResult(
            output="Error: steps cannot be empty",
            success=False,
            error="invalid_input",
        )
    
    # 验证steps格式
    for step in steps:
        if "id" not in step or "description" not in step:
            return ToolResult(
                output="Error: each step must have 'id' and 'description'",
                success=False,
                error="invalid_input",
            )
    
    # 构建plan结构(将在plan_prepare_node中注入state)
    # 这里只返回确认信息
    step_count = len(steps)
    serial_count = sum(1 for item in execution_order if isinstance(item, int))
    parallel_count = sum(1 for item in execution_order if isinstance(item, list))
    
    output_parts = [
        f"## Plan Created: {goal}",
        f"",
        f"**Execution Order**: {execution_order}",
        f"**Total Steps**: {step_count}",
        f"**Serial Groups**: {serial_count}",
        f"**Parallel Groups**: {parallel_count}",
        f"",
        f"**Steps**:",
    ]
    
    for step in steps:
        output_parts.append(f"- Step {step['id']}: {step['description']}")
    
    output_parts.append("")
    output_parts.append("Plan will be executed automatically.")
    
    return ToolResult(
        output="\n".join(output_parts),
        metadata={
            "type": "plan_execute",
            "goal": goal,
            "execution_order": execution_order,
            "steps": steps,
            "step_count": step_count,
        },
    )
