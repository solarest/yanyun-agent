"""基础设施层 - Session Spawn 工具

当需要并行处理相互独立的信息获取任务时，可以使用 sub-agent 来处理。

典型使用场景：
- 需要同时执行多个互不依赖的信息查询、资料阅读、文件分析
- 需要把一个可拆分目标拆成多个原子子任务，并发交给多个 sub-agent
- 某个原子子任务需要独立的上下文和工具集
- 任务执行时间较长，需要独立的流式输出
- 需要隔离任务状态，避免影响主 agent 的执行

重要约束：
- 一次 session_spawn 只代表一个原子子任务，不要把多个查询目标合并进同一个 sub-agent。
- 如果用户要求“近 10 天天气”“读取 5 个文件”“调研 3 个方案”等可拆分任务，主 agent 应在同一轮中并行调用多个 session_spawn，每个 sub-agent 只负责一天、一个文件、一个方案等。
- 主 agent 负责拆分任务、并行发起多个 sub-agent、汇总所有返回结果并给出最终答案。

同步阻塞模式：每个工具调用会等待对应 sub-agent 执行完成并返回结果；多个 session_spawn 工具调用会由工具执行节点并行执行。
"""

import logging
import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncIterator, Optional

from src.domain.entities.task import Task, TaskConfig, TaskStatus
from src.domain.entities.tool import ToolContext, ToolResult
from src.infrastructure.tools.decorator import tool

logger = logging.getLogger(__name__)


def _is_sqlite_task_repo(task_repo: Any) -> bool:
    return task_repo.__class__.__name__ == "SQLiteTaskRepository"


def _can_build_isolated_use_case(send_message_use_case: Any) -> bool:
    required_attrs = (
        "agent_repo",
        "session_repo",
        "message_repo",
        "task_repo",
        "event_emitter",
        "tool_registry",
        "skill_repo",
        "llm_provider",
        "running_tasks",
    )
    return all(hasattr(send_message_use_case, attr) for attr in required_attrs)


@asynccontextmanager
async def _sub_agent_runtime_scope(
    send_message_use_case: Any,
    task_repo: Any,
) -> AsyncIterator[tuple[Any, Any]]:
    """为一次 sub-agent 运行提供隔离的仓储会话。

    多个 session_spawn 会并行执行；生产环境中的 SQLite/SQLAlchemy AsyncSession
    不能跨并发任务共享。测试中的 mock repo 保持原路径，避免引入数据库依赖。
    """
    if not (_is_sqlite_task_repo(task_repo) and _can_build_isolated_use_case(send_message_use_case)):
        yield send_message_use_case, task_repo
        return

    from src.application.use_cases.send_message import SendMessageUseCase
    from src.infrastructure.database.session import AsyncSessionLocal
    from src.infrastructure.repositories.sqlite_agent_repo import SQLiteAgentRepository
    from src.infrastructure.repositories.sqlite_session_repo import SQLiteSessionRepository
    from src.infrastructure.repositories.sqlite_session_message_repo import (
        SQLiteSessionMessageRepository,
    )
    from src.infrastructure.repositories.sqlite_skill_repo import SQLiteSkillRepository
    from src.infrastructure.repositories.sqlite_task_repo import SQLiteTaskRepository

    async with AsyncSessionLocal() as db_session:
        isolated_task_repo = SQLiteTaskRepository(db_session)
        isolated_use_case = SendMessageUseCase(
            agent_repo=SQLiteAgentRepository(db_session),
            session_repo=SQLiteSessionRepository(db_session),
            message_repo=SQLiteSessionMessageRepository(db_session),
            task_repo=isolated_task_repo,
            event_emitter=send_message_use_case.event_emitter,
            tool_registry=send_message_use_case.tool_registry,
            skill_repo=SQLiteSkillRepository(db_session),
            llm_provider=send_message_use_case.llm_provider,
            running_tasks=send_message_use_case.running_tasks,
        )
        yield isolated_use_case, isolated_task_repo


async def _emit_safely(event_emitter: Any, task_id: str, event_type: str, payload: dict[str, Any]) -> None:
    emit_safe = getattr(event_emitter, "emit_safe", None)
    try:
        if callable(emit_safe) and hasattr(type(event_emitter), "emit_safe"):
            await emit_safe(task_id, event_type, payload)
        else:
            await event_emitter.emit(task_id, event_type, payload)
    except Exception as exc:
        logger.warning("session_spawn event emit failed: %s", exc)


@tool(
    name="session_spawn",
    description=(
        "生成一个 sub-agent 执行一个原子、独立、可并行的信息获取子任务。"
        "重要：一次 session_spawn 只处理一个子任务；不要把多个日期、多个文件、多个主题或多个查询合并到同一个 sub-agent。"
        "当任务可拆分时，主 agent 应在同一轮并行调用多个 session_spawn，例如近 10 天天气应创建 10 个 sub-agent，"
        "每个负责 1 天，然后由主 agent 汇总结果。同步阻塞模式：单个调用等待该 sub-agent 完成；多个调用会并行执行。"
    ),
    category="session",
    returns="Sub-agent 执行结果",
    # 装饰器超时需大于内部轮询 max_wait（300s），让内部 TimeoutError 优先触发以返回友好错误
    timeout_ms=600000,
    max_calls_per_minute=10,
    sandboxed=False,
)
async def session_spawn(
    description: str,
    tools: Optional[list[str]] = None,
    context: Optional[ToolContext] = None,
) -> ToolResult:
    """生成 sub-agent 执行一个原子子任务

    当主 agent 遇到可拆分、可并行的信息获取任务时，可以使用此工具创建 sub-agent。
    Sub-agent 会复用主 agent 的核心逻辑，但拥有独立的执行上下文和工具集。

    使用原则：
    - 一个 session_spawn = 一个原子子任务。
    - 不要让一个 sub-agent 负责多个独立查询目标。
    - 如果任务包含 N 个独立目标，应在同一轮发起 N 个 session_spawn 工具调用。
    - sub-agent 只负责收集/分析并返回结果；主 agent 负责拆分、调度、汇总和最终作答。

    典型场景：
    - 查询近 10 天某地天气：发起 10 个 session_spawn，每个查询 1 天
    - 读取多个文件：发起多个 session_spawn，每个读取/总结 1 个文件
    - 调研多个方案或来源：发起多个 session_spawn，每个负责 1 个方案或来源
    - 需要隔离的任务，避免影响主 agent 状态

    Args:
        description: 单个原子子任务描述，必须只包含一个独立目标。示例："查询 2026-05-21 杭州天气并返回日期、最高温、最低温、天气状况"。不要写成"查询 2026-05-12 到 2026-05-21 每天的天气"。
        tools: 指定 sub-agent 可用的工具列表（可选）
               - 如果不指定，sub-agent 将使用全部可用工具（排除 session_spawn, task_create, task_update）
               - 如果指定，sub-agent 只能使用列表中的工具
        context: 工具执行上下文（由框架自动注入）

    Returns:
        ToolResult: sub-agent 执行结果
            - success=True: 任务成功完成，output 包含执行结果
            - success=False: 任务失败，output 和 error 包含错误信息
    """
    # 参数校验
    if not description or not description.strip():
        return ToolResult(
            output="Error: description cannot be empty",
            success=False,
            error="invalid_input",
        )

    # 从 context 获取必要依赖
    if not context:
        return ToolResult(
            output="Error: context is required for session_spawn",
            success=False,
            error="missing_context",
        )

    send_message_use_case = context.extra.get("send_message_use_case")
    if not send_message_use_case:
        return ToolResult(
            output="Error: send_message_use_case not available in context",
            success=False,
            error="missing_use_case",
        )

    task_repo = context.extra.get("task_repo")
    if not task_repo:
        return ToolResult(
            output="Error: task_repo not available in context",
            success=False,
            error="missing_task_repo",
        )

    event_emitter = context.extra.get("event_emitter")
    if not event_emitter:
        return ToolResult(
            output="Error: event_emitter not available in context",
            success=False,
            error="missing_event_emitter",
        )

    # 获取父 agent 上下文
    parent_agent_id = context.extra.get("parent_agent_id", "")
    parent_session_id = context.extra.get("parent_session_id", "")
    parent_task_id = context.extra.get("parent_task_id", context.task_id)
    parent_state = context.extra.get("parent_state", {})

    if not parent_agent_id or not parent_session_id:
        return ToolResult(
            output="Error: parent agent or session info missing",
            success=False,
            error="missing_parent_info",
        )

    sub_task_id = f"sub-{uuid.uuid4().hex[:12]}"

    try:
        from src.infrastructure.llm.config import LLMSettings

        effective_model = parent_state.get("model") or LLMSettings().default_model

        async with _sub_agent_runtime_scope(send_message_use_case, task_repo) as (
            runtime_use_case,
            runtime_task_repo,
        ):
            # 1. 创建 sub-task
            sub_task = Task(
                id=sub_task_id,
                message=description,
                workspace=context.workspace,
                status=TaskStatus.RUNNING,
                model=effective_model,
                config=TaskConfig(max_turns=50),
                max_turns=50,
                agent_id=parent_agent_id,
                session_id=parent_session_id,
                started_at=datetime.now(),
            )
            await runtime_task_repo.add(sub_task)

            # 2. 发射 sub_agent:started 事件
            await _emit_safely(
                event_emitter,
                parent_task_id,
                "sub_agent:started",
                {
                    "sub_task_id": sub_task_id,
                    "description": description,
                    "parent_task_id": parent_task_id,
                },
            )

            # 3. 调用 SendMessageUseCase 的 sub-agent 模式
            result = await runtime_use_case.execute(
                agent_id=parent_agent_id,
                session_id=parent_session_id,
                content=description,
                model=effective_model,
                max_turns=50,
                workspace=context.workspace,
                # Sub-agent 模式标志
                is_sub_agent=True,
                parent_task_id=parent_task_id,
                sub_agent_description=description,
                parent_system_prompt=parent_state.get("system_prompt", ""),
                sub_task=sub_task,
                allowed_tools=tools,
            )

            # 4. 提取结果
            task_id = result.get("task_id", sub_task_id)

            max_wait = 300  # 最多等待 5 分钟
            asyncio_task = result.get("asyncio_task")
            if asyncio_task is not None:
                await asyncio.wait_for(asyncio_task, timeout=max_wait)
            else:
                waited = 0
                while waited < max_wait:
                    completed_task = await runtime_task_repo.get_by_id(task_id)
                    if completed_task and completed_task.completed_at:
                        break
                    await asyncio.sleep(1)
                    waited += 1

            completed_task = await runtime_task_repo.get_by_id(task_id)
            if not completed_task or not completed_task.completed_at:
                raise TimeoutError(
                    f"Sub-agent execution timeout after {max_wait}s")

            # 5. 发射 sub_agent:completed/failed 事件
            if completed_task.status == TaskStatus.FAILED:
                await _emit_safely(
                    event_emitter,
                    parent_task_id,
                    "sub_agent:failed",
                    {
                        "sub_task_id": sub_task_id,
                        "error": completed_task.error or "Unknown error",
                        "parent_task_id": parent_task_id,
                    },
                )

                return ToolResult(
                    output=(
                        f"Sub-agent failed.\n"
                        f"Task ID: {sub_task_id}\n"
                        f"Error: {completed_task.error or 'Unknown error'}"
                    ),
                    success=False,
                    error=completed_task.error,
                    metadata={
                        "type": "session_spawn",
                        "status": "failed",
                        "sub_task_id": sub_task_id,
                    },
                )
            await _emit_safely(
                event_emitter,
                parent_task_id,
                "sub_agent:completed",
                {
                    "sub_task_id": sub_task_id,
                    "result": completed_task.result or "No result",
                    "parent_task_id": parent_task_id,
                },
            )

            return ToolResult(
                output=(
                    f"Sub-agent completed.\n"
                    f"Task ID: {sub_task_id}\n"
                    f"Result:\n\n{completed_task.result or 'No result'}"
                ),
                success=True,
                metadata={
                    "type": "session_spawn",
                    "status": "completed",
                    "sub_task_id": sub_task_id,
                },
            )

    except Exception as e:
        logger.exception("session_spawn failed: %s", e)

        # 发射 sub_agent:failed 事件
        await _emit_safely(
            event_emitter,
            parent_task_id,
            "sub_agent:failed",
            {
                "sub_task_id": sub_task_id,
                "error": str(e),
                "parent_task_id": parent_task_id,
            },
        )

        return ToolResult(
            output=f"Error: Failed to spawn sub-agent: {e}",
            success=False,
            error=str(e),
        )
