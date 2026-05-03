"""基础设施层 - 任务规划工具

将复杂任务分解为可执行的步骤计划。
注意：plan_execute 工具通过闭包工厂在 SendMessageUseCase 中动态创建，
     不再在此处静态定义。
"""

import logging
from typing import Optional

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
