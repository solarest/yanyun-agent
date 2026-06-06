"""基础设施层 - Team 工具集

团队协作工具，供 Leader 和 Member 在 team mode 下使用。

Leader 工具:
- update_team_tasks: 持续迭代团队任务列表
- assign_team_task: 指派任务给对应成员（同 member 串行，不同 member 并行）
- check_team_reports: 检查成员上报的结果

Member 工具:
- report_team_task: 上报执行结果给 Leader
"""

import asyncio
import logging
import uuid
from typing import Optional

from src.domain.entities.tool import ToolContext, ToolResult
from src.domain.team.message import TeamMessage
from src.domain.team.values import MessageType
from src.infrastructure.tools.decorator import tool

logger = logging.getLogger(__name__)

# ── 按 agent_id 的锁，保证同一 member 串行执行 ──
_member_locks: dict[str, asyncio.Lock] = {}

# ── Leader 工具 ─────────────────────────────────────────────


@tool(
    name="update_team_tasks",
    description=(
        "Update the team task list. Use this to add, remove, update status, "
        "or reorder tasks. This is your central coordination artifact — maintain "
        "a current view of all team work here.\n\n"
        "Each task should have: id (unique identifier), description (what needs "
        "to be done), assigned_to (agent_id of the member, or null if unassigned), "
        "status (pending, in_progress, completed, failed)."
    ),
    category="team",
    returns="Updated task list confirmation",
    timeout_ms=10000,
)
async def update_team_tasks(
    tasks: list[dict],
    context: Optional[ToolContext] = None,
) -> ToolResult:
    """更新团队任务列表"""
    if not tasks:
        return ToolResult(
            output="Error: tasks cannot be empty",
            success=False,
            error="invalid_input",
        )

    validated = []
    for t in tasks:
        task_id = t.get("id", str(uuid.uuid4().hex[:8]))
        description = t.get("description", "")
        if not description.strip():
            return ToolResult(
                output=f"Error: task {task_id} description cannot be empty",
                success=False,
                error="invalid_input",
            )
        status = t.get("status", "pending")
        if status not in ("pending", "in_progress", "completed", "failed"):
            status = "pending"

        validated.append({
            "id": task_id,
            "description": description.strip(),
            "assigned_to": t.get("assigned_to"),
            "status": status,
        })

    status_counts = {"pending": 0, "in_progress": 0, "completed": 0, "failed": 0}
    lines = ["## Team Task List\n"]
    for t in validated:
        status_counts[t["status"]] = status_counts.get(t["status"], 0) + 1
        assignee = f" → {t['assigned_to']}" if t.get("assigned_to") else ""
        lines.append(f"- [{t['status']}] Task {t['id']}: {t['description']}{assignee}")

    summary = (
        f"\n---\nSummary: {len(validated)} tasks — "
        f"{status_counts['completed']} completed, "
        f"{status_counts['in_progress']} in progress, "
        f"{status_counts['pending']} pending, "
        f"{status_counts['failed']} failed"
    )
    lines.append(summary)

    return ToolResult(
        output="\n".join(lines),
        metadata={
            "type": "update_team_tasks",
            "tasks": validated,
            "task_count": len(validated),
            "status_counts": status_counts,
        },
    )


@tool(
    name="assign_team_task",
    description=(
        "Assign a task to a team member and wait for the result. "
        "This spawns the member agent, waits for execution to complete, "
        "and returns the result. Call multiple times in parallel for "
        "multiple members.\n\n"
        "Provide the member's agent_id and a clear task description."
    ),
    category="team",
    returns="Member execution result",
    timeout_ms=600000,  # 同步等待 member 完成，最多 10 分钟
)
async def assign_team_task(
    agent_id: str,
    task_description: str,
    request_id: Optional[str] = None,
    context: Optional[ToolContext] = None,
) -> ToolResult:
    """指派任务给团队成员（同步阻塞模式）

    类似 session_spawn：启动 member agent loop，等待完成，返回结果。
    多个 assign_team_task 在同一 turn 中并行执行。

    Args:
        agent_id: 目标成员的 Agent ID
        task_description: 任务描述
        request_id: 请求 ID（可选）
        context: 工具执行上下文（由框架自动注入）
    """
    if not agent_id or not agent_id.strip():
        return ToolResult(
            output="Error: agent_id cannot be empty",
            success=False,
            error="invalid_input",
        )

    if not task_description or not task_description.strip():
        return ToolResult(
            output="Error: task_description cannot be empty",
            success=False,
            error="invalid_input",
        )

    if not context:
        return ToolResult(
            output="Error: context is required",
            success=False,
            error="missing_context",
        )

    message_bus = context.extra.get("team_message_bus")
    team_id = context.extra.get("team_id", "")
    leader_agent_id = context.extra.get("leader_agent_id",
                                         context.extra.get("parent_agent_id", ""))
    # Member 自有 session：按 execution 隔离，同一 execution 内多次调用保留上下文
    parent_task_id = context.extra.get("parent_task_id", context.task_id)
    member_session_id = f"team-{parent_task_id}-member-{agent_id.strip()}"

    if not request_id:
        request_id = f"req_{uuid.uuid4().hex[:12]}"

    target_agent_id = agent_id.strip()

    # 发送 TASK_ASSIGN 到 bus（记录用）
    message = TeamMessage(
        team_id=team_id,
        sender_agent_id=leader_agent_id,
        receiver_agent_id=target_agent_id,
        message_type=MessageType.TASK_ASSIGN,
        content=task_description.strip(),
        request_id=request_id,
    )
    await message_bus.send(message)

    logger.info(
        "assign_team_task: leader → %s [%s] — spawning sync member runner (team=%s)",
        target_agent_id, request_id, team_id,
    )

    # ── 同步启动 member agent loop ──
    from datetime import datetime as dt
    from src.domain.aggregates.task.task import Task, TaskConfig, TaskStatus
    from src.application.services.agent_loop_runner import AgentLoopRunner
    from src.application.services.task_completion_service import TaskCompletionService
    from src.infrastructure.agent.prompt_context_impl import PromptContextImpl
    from src.infrastructure.database.session import async_engine
    from src.infrastructure.repositories.sqlite_task_repo import SQLiteTaskRepository
    from src.infrastructure.repositories.sqlite_session_repo import SQLiteSessionRepository
    from src.infrastructure.repositories.sqlite_session_message_repo import (
        SQLiteSessionMessageRepository,
    )
    from sqlalchemy.ext.asyncio import AsyncSession as SAAsyncSession

    sub_task_id = f"team-sub-{uuid.uuid4().hex[:12]}"
    workspace = context.workspace
    event_emitter = context.extra.get("event_emitter")

    # ── 发射 team:task:assigned 事件（供前端连接 member SSE stream）──
    if event_emitter:
        try:
            await event_emitter.emit(
                parent_task_id,
                "team:task:assigned",
                {
                    "team_id": team_id,
                    "agent_id": target_agent_id,
                    "task_id": sub_task_id,
                    "request_id": request_id,
                    "description": task_description.strip(),
                },
            )
        except Exception:
            logger.warning("Failed to emit team:task:assigned", exc_info=True)

    # ── 按 agent_id 串行化：同一 member 排队执行 ──
    lock = _member_locks.setdefault(target_agent_id, asyncio.Lock())
    async with lock:
        logger.info(
            "assign_team_task: member %s acquired lock [%s] — executing task",
            target_agent_id, request_id,
        )

        # 创建独立 DB session
        member_db = SAAsyncSession(async_engine)
        try:
            member_task_repo = SQLiteTaskRepository(member_db)
            member_session_repo = SQLiteSessionRepository(member_db)
            member_message_repo = SQLiteSessionMessageRepository(member_db)

            sub_task = Task(
                id=sub_task_id,
                message=task_description.strip(),
                workspace=workspace,
                status=TaskStatus.RUNNING,
                model="",
                config=TaskConfig(max_turns=50),
                max_turns=50,
                agent_id=target_agent_id,
                session_id=member_session_id,
                started_at=dt.now(),
            )
            sub_task = await member_task_repo.add(sub_task)

            completion_service = TaskCompletionService(
                message_repo=member_message_repo,
                task_repo=member_task_repo,
                session_repo=member_session_repo,
            )

            # 获取 member 工具集：从 GLOBAL 注册表过滤（不能用 leader 的过滤后注册表）
            from src.infrastructure.tools.registry import ToolRegistry
            from src.presentation.dependencies import create_tool_registry
            member_registry = ToolRegistry()
            global_registry = create_tool_registry()
            for tool in global_registry.list_tools():
                if tool.name in ("update_team_tasks", "assign_team_task",
                                 "check_team_reports", "session_spawn",
                                 "task_create", "task_update"):
                    continue
                member_registry.register(tool)

            # 获取 llm_provider（从 context 或全局单例）
            from src.presentation.dependencies import get_llm_provider, get_llm_settings
            llm_provider = get_llm_provider()
            llm_settings = get_llm_settings()

            from src.infrastructure.repositories.sqlite_agent_repo import SQLiteAgentRepository
            agent_repo = SQLiteAgentRepository(member_db)

            member_runner = AgentLoopRunner(
                agent_repo=agent_repo,
                llm_provider=llm_provider,
                prompt_context=PromptContextImpl(),
                message_repo=member_message_repo,
                skill_repo=None,
                task_repo=member_task_repo,
                session_repo=member_session_repo,
                event_emitter=event_emitter,
                tool_registry=member_registry,
                workflow_builder=None,
                task_completion_service=completion_service,
                default_model=llm_settings.default_model,
            )

            # 构建 member 的 team_context
            from src.domain.team.orchestrator import TeamOrchestrator
            from src.domain.team.member import TeamMember as TMember
            from src.domain.team.entity import Team as TeamEntity
            from src.domain.team.values import TeamRole
            member_entity = TMember(team_id=team_id, agent_id=target_agent_id, role=TeamRole.MEMBER)
            member_context = TeamOrchestrator().build_member_prompt_additions(
                TeamEntity(id=team_id, name=team_id),
                member_entity,
            )

            # 运行 member（member 自有 session，持久化消息以保留多次调用的上下文）
            await member_runner.run(
                agent_id=target_agent_id,
                session_id=member_session_id,
                task=sub_task,
                content=task_description.strip(),
                model=llm_settings.default_model,
                max_turns=50,
                workspace=workspace,
                team_mode=True,
                team_id=team_id,
                team_role="member",
                team_message_bus=message_bus,
                team_context=member_context,
                leader_agent_id=leader_agent_id,
                persist_session_messages=True,
            )

            # 获取结果
            completed_task = await member_task_repo.get_by_id(sub_task_id)
            result_text = completed_task.result if completed_task else "No result"

            is_failed = completed_task and completed_task.status == TaskStatus.FAILED
            status_str = "failed" if is_failed else "completed"

            # ── 发射 team:task:reported 事件 ──
            if event_emitter:
                try:
                    report_payload: dict = {
                        "team_id": team_id,
                        "agent_id": target_agent_id,
                        "task_id": sub_task_id,
                        "request_id": request_id,
                        "status": status_str,
                        "result": result_text if not is_failed else "",
                    }
                    if is_failed:
                        report_payload["error"] = completed_task.error if completed_task else "Unknown"
                    await event_emitter.emit(parent_task_id, "team:task:reported", report_payload)
                except Exception:
                    logger.warning("Failed to emit team:task:reported", exc_info=True)

            if is_failed:
                return ToolResult(
                    output=f"Member `{target_agent_id}` failed: {completed_task.error or 'Unknown'}",
                    success=False,
                    error=completed_task.error,
                    metadata={"type": "assign_team_task", "agent_id": target_agent_id,
                              "request_id": request_id, "status": "failed"},
                )

            return ToolResult(
                output=f"Member `{target_agent_id}` completed.\n\nResult:\n{result_text}",
                success=True,
                metadata={"type": "assign_team_task", "agent_id": target_agent_id,
                          "request_id": request_id, "status": "completed"},
            )

        except Exception as e:
            logger.exception("assign_team_task failed: %s", e)
            # ── 发射 team:task:reported (failed) ──
            if event_emitter:
                try:
                    await event_emitter.emit(
                        parent_task_id,
                        "team:task:reported",
                        {
                            "team_id": team_id,
                            "agent_id": target_agent_id,
                            "task_id": sub_task_id,
                            "request_id": request_id,
                            "status": "failed",
                            "error": str(e),
                        },
                    )
                except Exception:
                    pass
            return ToolResult(
                output=f"Error: {e}",
                success=False,
                error=str(e),
            )
        finally:
            await member_db.close()


@tool(
    name="check_team_reports",
    description=(
        "Check for pending task reports from team members. Reads all unread "
        "TASK_REPORT messages from the team message bus.\n\n"
        "Call this after assigning tasks to check if members have reported results. "
        "Returns a list of all pending reports with their results."
    ),
    category="team",
    returns="List of pending member reports",
    timeout_ms=10000,
)
async def check_team_reports(
    context: Optional[ToolContext] = None,
) -> ToolResult:
    """检查成员上报结果

    Leader 使用此工具轮询消息总线中来自 member 的 TASK_REPORT 消息。

    Args:
        context: 工具执行上下文（由框架自动注入）
    """
    if not context:
        return ToolResult(
            output="Error: context is required",
            success=False,
            error="missing_context",
        )

    message_bus = context.extra.get("team_message_bus")
    if not message_bus:
        return ToolResult(
            output="Error: team_message_bus not available — not in team mode",
            success=False,
            error="missing_message_bus",
        )

    leader_agent_id = context.extra.get("leader_agent_id",
                                         context.extra.get("parent_agent_id", ""))

    # 收集所有未读的 TASK_REPORT 消息
    reports: list[dict] = []
    while True:
        msg = await message_bus.poll(leader_agent_id)
        if msg is None:
            break
        msg_type_str = msg.message_type.value if hasattr(msg.message_type, 'value') else str(msg.message_type)
        if msg_type_str == MessageType.TASK_REPORT.value or msg_type_str == 'task_report':
            reports.append({
                "request_id": msg.request_id,
                "sender_agent_id": msg.sender_agent_id,
                "content": msg.content,
            })

    if not reports:
        return ToolResult(
            output="No pending reports from team members yet. "
                   "Members may still be working on their tasks.",
            metadata={
                "type": "check_team_reports",
                "report_count": 0,
                "reports": [],
            },
        )

    lines = [f"## Team Reports ({len(reports)} pending)\n"]
    for i, r in enumerate(reports, 1):
        lines.append(f"### Report {i}")
        lines.append(f"- **From**: `{r['sender_agent_id']}`")
        lines.append(f"- **Request ID**: `{r['request_id']}`")
        lines.append(f"- **Result**:\n{r['content']}")
        lines.append("")

    return ToolResult(
        output="\n".join(lines),
        metadata={
            "type": "check_team_reports",
            "report_count": len(reports),
            "reports": reports,
        },
    )


# ── Member 工具 ──────────────────────────────────────────────


@tool(
    name="report_team_task",
    description=(
        "Report your task execution results back to the team leader. "
        "Call this when you have completed (or failed) the assigned task. "
        "Include the request_id from the original assignment for correlation. "
        "Your result is sent through the team message bus to the leader."
    ),
    category="team",
    returns="Report confirmation",
    timeout_ms=10000,
)
async def report_team_task(
    result: str,
    request_id: Optional[str] = None,
    status: str = "completed",
    context: Optional[ToolContext] = None,
) -> ToolResult:
    """上报任务结果给 Leader

    Member 使用此工具将执行结果发送给 Leader。

    Args:
        result: 任务执行结果
        request_id: 原始任务的 request_id（用于关联）
        status: 执行状态 — completed / failed
        context: 工具执行上下文（由框架自动注入）
    """
    if not result or not result.strip():
        return ToolResult(
            output="Error: result cannot be empty",
            success=False,
            error="invalid_input",
        )

    if status not in ("completed", "failed"):
        return ToolResult(
            output="Error: status must be 'completed' or 'failed'",
            success=False,
            error="invalid_input",
        )

    if not context:
        return ToolResult(
            output="Error: context is required",
            success=False,
            error="missing_context",
        )

    message_bus = context.extra.get("team_message_bus")
    if not message_bus:
        return ToolResult(
            output="Error: team_message_bus not available — not in team mode",
            success=False,
            error="missing_message_bus",
        )

    team_id = context.extra.get("team_id", "")
    leader_agent_id = context.extra.get("leader_agent_id", "")
    my_agent_id = context.extra.get("agent_id", "")

    if not leader_agent_id:
        return ToolResult(
            output="Error: leader_agent_id not available in team context",
            success=False,
            error="missing_leader_info",
        )

    message = TeamMessage(
        team_id=team_id,
        sender_agent_id=my_agent_id,
        receiver_agent_id=leader_agent_id,
        message_type=MessageType.TASK_REPORT,
        content=result.strip(),
        request_id=request_id,
    )

    await message_bus.send(message)

    logger.info(
        "report_team_task: %s → leader [%s] status=%s (team=%s)",
        my_agent_id, request_id, status, team_id,
    )

    return ToolResult(
        output=(
            f"Result reported to team leader.\n"
            f"Request ID: `{request_id or 'N/A'}`\n"
            f"Status: {status}"
        ),
        metadata={
            "type": "report_team_task",
            "request_id": request_id,
            "status": status,
            "result": result.strip(),
        },
    )
