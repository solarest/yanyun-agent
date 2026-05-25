"""基础设施层 - 任务创建工具

创建多步骤任务记录，用于跟踪复杂任务的执行进度。
"""

import logging
from typing import Optional

from src.domain.entities.tool import ToolContext, ToolResult
from src.infrastructure.tools.decorator import tool

logger = logging.getLogger(__name__)


@tool(
    name="task_create",
    description="Create a multi-step task list to track execution progress of complex tasks. Create tasks before starting multi-step workflows.",
    category="task",
    returns="Created task list",
    timeout_ms=5000,
)
async def task_create(
    goal: str,
    tasks: list[dict],
    context: Optional[ToolContext] = None,
) -> ToolResult:
    """创建多步骤任务记录

    Args:
        goal: 任务目标描述
        tasks: 任务列表，每个任务包含 id, description, depends_on 字段
               示例: [{"id": 1, "description": "分析需求", "depends_on": []}]
    """
    if not goal.strip():
        return ToolResult(
            output="Error: goal cannot be empty",
            success=False,
            error="invalid_input",
        )

    if not tasks:
        return ToolResult(
            output="Error: tasks cannot be empty",
            success=False,
            error="invalid_input",
        )

    # 验证和标准化任务
    validated_tasks = []
    task_ids = set()

    for i, task in enumerate(tasks, 1):
        task_id = task.get("id", i)
        description = task.get("description", "")
        depends_on = task.get("depends_on", [])

        if not description.strip():
            return ToolResult(
                output=f"Error: task {task_id} description cannot be empty",
                success=False,
                error="invalid_input",
            )

        if task_id in task_ids:
            return ToolResult(
                output=f"Error: duplicate task id {task_id}",
                success=False,
                error="invalid_input",
            )

        task_ids.add(task_id)
        validated_tasks.append({
            "id": task_id,
            "description": description.strip(),
            "depends_on": depends_on,
            "status": "pending",
        })

    # 验证依赖关系
    for task in validated_tasks:
        for dep_id in task["depends_on"]:
            if dep_id not in task_ids:
                return ToolResult(
                    output=f"Error: task {task['id']} depends on non-existent task {dep_id}",
                    success=False,
                    error="invalid_input",
                )

    # 构建输出
    output_parts = [f"## Task List: {goal}\n"]
    for task in validated_tasks:
        deps_str = ""
        if task["depends_on"]:
            deps = ", ".join(str(d) for d in task["depends_on"])
            deps_str = f" (depends on: {deps})"
        output_parts.append(
            f"- [ ] Task {task['id']}: {task['description']}{deps_str}")

    return ToolResult(
        output="\n".join(output_parts),
        metadata={
            "type": "task_create",
            "goal": goal,
            "tasks": validated_tasks,
            "task_count": len(validated_tasks),
        },
    )
