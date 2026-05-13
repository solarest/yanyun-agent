"""基础设施层 - Session Spawn 工具

生成一个新的 sub-agent 来执行特定任务。
同步阻塞模式，等待 sub-agent 执行完成并返回结果。
"""

import logging
from typing import Optional

from src.domain.entities.tool import ToolContext, ToolResult
from src.infrastructure.tools.decorator import tool

logger = logging.getLogger(__name__)


@tool(
    name="session_spawn",
    description="生成一个新的 sub-agent 来执行特定任务。当需要处理独立任务时使用。同步阻塞模式，等待 sub-agent 执行完成。",
    category="session",
    returns="Sub-agent 执行结果",
    timeout_ms=60000,
    max_calls_per_minute=10,
    sandboxed=False,
)
async def session_spawn(
    description: str,
    tools: Optional[list[str]] = None,
    context: Optional[ToolContext] = None,
) -> ToolResult:
    """生成 sub-agent 执行特定任务

    Args:
        description: 任务描述，告诉 sub-agent 需要做什么
        tools: 指定 sub-agent 可用的工具列表，默认为全部可用工具（排除 session_spawn, task_create, task_update）

    Returns:
        ToolResult: sub-agent 执行结果
    """
    # 参数校验
    if not description or not description.strip():
        return ToolResult(
            output="Error: description cannot be empty",
            success=False,
            error="invalid_input",
        )

    # 从 context 获取 sub_agent_launcher
    if not context:
        return ToolResult(
            output="Error: context is required for session_spawn",
            success=False,
            error="missing_context",
        )

    launcher = context.extra.get("sub_agent_launcher")
    if not launcher:
        return ToolResult(
            output="Error: sub_agent_launcher not available in context",
            success=False,
            error="missing_launcher",
        )

    # 获取父 agent 状态和上下文
    parent_state = context.extra.get("parent_state")
    if not parent_state:
        return ToolResult(
            output="Error: parent_state not available in context",
            success=False,
            error="missing_parent_state",
        )

    parent_agent_id = context.extra.get("parent_agent_id", "")
    parent_session_id = context.extra.get("parent_session_id", "")
    parent_task_id = context.extra.get("parent_task_id", context.task_id)
    user_message = context.extra.get("user_message", "")

    if not parent_agent_id or not parent_session_id:
        return ToolResult(
            output="Error: parent agent or session info missing",
            success=False,
            error="missing_parent_info",
        )

    try:
        # 调用 sync 模式启动 sub-agent
        result = await launcher.launch_sync(
            description=description.strip(),
            parent_state=parent_state,
            parent_agent_id=parent_agent_id,
            parent_session_id=parent_session_id,
            parent_task_id=parent_task_id,
            workspace=context.workspace,
            allowed_tools=tools,
            user_message=user_message,
        )

        # 构建输出
        status = result.get("status", "unknown")
        sub_task_id = result.get("sub_task_id", "")

        if status == "completed":
            output = (
                f"Sub-agent completed.\n"
                f"Task ID: {sub_task_id}\n"
                f"Result:\n\n{result.get('result', 'No result')}"
            )
        elif status == "failed":
            output = (
                f"Sub-agent failed.\n"
                f"Task ID: {sub_task_id}\n"
                f"Error: {result.get('error', 'Unknown error')}"
            )
        else:
            output = f"Sub-agent status: {status}\nTask ID: {sub_task_id}"

        return ToolResult(
            output=output,
            success=status == "completed",
            error=result.get("error") if status == "failed" else None,
            metadata={
                "type": "session_spawn",
                "status": status,
                "sub_task_id": sub_task_id,
            },
        )

    except Exception as e:
        logger.exception("session_spawn failed: %s", e)
        return ToolResult(
            output=f"Error: Failed to spawn sub-agent: {e}",
            success=False,
            error=str(e),
        )
