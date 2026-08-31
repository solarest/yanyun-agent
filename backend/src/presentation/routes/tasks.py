"""表现层 - 任务 CRUD 路由"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request, status

from src.application.dtos.approval_dto import ApprovalDecisionDTO
from src.application.dtos.task_dto import (
    CreateTaskDTO,
    TaskListResponseDTO,
    TaskResponseDTO,
)
from src.application.tasks.management import (
    AgentNotFoundError,
    TaskManagementUseCase,
    TaskNotFoundError,
    TaskNotRunningError,
)
from src.domain.repositories.task_repository import ITaskRepository
from src.infrastructure.tools.confirmation.store import (
    PendingApprovalRegistry,
)
from src.presentation.dependencies import (
    get_pending_approval_registry,
    get_send_message_use_case,
    get_task_management_use_case,
    get_task_repository,
)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


@router.post(
    "",
    response_model=TaskResponseDTO,
    status_code=status.HTTP_201_CREATED,
    summary="创建任务",
    description="创建一个新的 Agent 任务，可选关联 Agent",
    responses={
        404: {"description": "关联的 Agent 不存在"},
    },
)
async def create_task(
    dto: CreateTaskDTO,
    task_uc: TaskManagementUseCase = Depends(get_task_management_use_case),
):
    """创建任务

    创建任务实体并保存到数据库。
    如果指定了 agent_id，会校验 Agent 是否存在。
    任务创建后处于 idle 状态，等待执行。
    """
    try:
        task = await task_uc.create(
            message=dto.message,
            workspace=dto.workspace,
            agent_id=dto.agent_id,
            model=dto.model or "gpt-4",
            max_turns=dto.max_turns or 100,
        )
    except AgentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "AGENT_NOT_FOUND",
                    "message": str(e),
                }
            },
        )

    return TaskResponseDTO(
        id=task.id,
        message=task.message,
        workspace=task.workspace,
        status=task.status.value,
        model=task.model,
        current_turn=task.current_turn,
        max_turns=task.max_turns,
        agent_id=task.agent_id,
        created_at=task.created_at.isoformat(),
    )


@router.get(
    "",
    response_model=TaskListResponseDTO,
    summary="获取任务列表",
    description="分页获取任务列表",
)
async def list_tasks(
    page: int = 1,
    page_size: int = 20,
    task_repo: ITaskRepository = Depends(get_task_repository),
):
    """获取任务列表"""
    offset = (page - 1) * page_size
    tasks = await task_repo.list_all(limit=page_size, offset=offset)

    return TaskListResponseDTO(
        data=[
            TaskResponseDTO(
                id=t.id,
                message=t.message,
                workspace=t.workspace,
                status=t.status.value,
                model=t.model,
                current_turn=t.current_turn,
                max_turns=t.max_turns,
                agent_id=t.agent_id,
                result=t.result,
                error=t.error,
                cost=t.cost.to_dict(),
                created_at=t.created_at.isoformat(),
                started_at=t.started_at.isoformat() if t.started_at else None,
                completed_at=t.completed_at.isoformat() if t.completed_at else None,
            )
            for t in tasks
        ],
        total=len(tasks),  # 简化：实际应该查询总数
    )


@router.get(
    "/{task_id}",
    response_model=TaskResponseDTO,
    summary="获取任务详情",
    responses={404: {"description": "任务不存在"}},
)
async def get_task(
    task_id: str,
    task_repo: ITaskRepository = Depends(get_task_repository),
):
    """获取任务详情"""
    task = await task_repo.get_by_id(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "TASK_NOT_FOUND", "message": "任务不存在"}},
        )

    return TaskResponseDTO(
        id=task.id,
        message=task.message,
        workspace=task.workspace,
        status=task.status.value,
        model=task.model,
        current_turn=task.current_turn,
        max_turns=task.max_turns,
        agent_id=task.agent_id,
        result=task.result,
        error=task.error,
        cost=task.cost.to_dict(),
        created_at=task.created_at.isoformat(),
        started_at=task.started_at.isoformat() if task.started_at else None,
        completed_at=task.completed_at.isoformat() if task.completed_at else None,
    )


@router.post(
    "/{task_id}/cancel",
    status_code=status.HTTP_200_OK,
    summary="取消任务",
    description="取消正在运行的 Agent Loop 任务",
    responses={
        404: {"description": "任务不存在"},
        409: {"description": "任务不在可取消状态"},
    },
)
async def cancel_task(
    task_id: str,
    task_uc: TaskManagementUseCase = Depends(get_task_management_use_case),
):
    """取消运行中的任务"""
    try:
        result = await task_uc.cancel(task_id)
    except TaskNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "TASK_NOT_FOUND", "message": "任务不存在"}},
        )
    except TaskNotRunningError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "TASK_NOT_RUNNING", "message": "任务不在可取消状态"}},
        )

    return {"message": "cancel requested", "task_id": result["task_id"]}


@router.post(
    "/{task_id}/approvals",
    status_code=status.HTTP_200_OK,
    summary="提交命令确认决策",
    description="对挂起等待确认的危险 shell 命令提交用户决策"
    "（本次允许 / 全部允许 / 拒绝），从本地状态快照继续执行。",
    responses={404: {"description": "无此待确认调用"}},
)
async def submit_approval(
    task_id: str,
    dto: ApprovalDecisionDTO,
    registry: PendingApprovalRegistry = Depends(get_pending_approval_registry),
    request: Request = None,
):
    """提交命令确认决策。

    从任务本地快照读取待确认工具调用并在后台继续执行。
    进程内注册表仅用于清理旧登记，进程重启后仍可通过快照恢复。
    """
    resume_use_case = get_send_message_use_case(request) if request else None
    if resume_use_case is None or resume_use_case.loop_runner is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NO_PENDING_APPROVAL", "message": "无此待确认调用"}},
        )

    from src.infrastructure.database.session import AsyncSessionLocal
    from src.infrastructure.repositories.sqlite_task_repo import SQLiteTaskRepository

    async with AsyncSessionLocal() as db:
        task_repo = SQLiteTaskRepository(db)
        task = await task_repo.get_by_id(task_id)

    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "NO_PENDING_APPROVAL", "message": "无此待确认调用"}},
        )

    file_storage = resume_use_case._file_storage
    task_dir = file_storage.base_path / task.session_id / task.id
    checkpoint = file_storage.read_latest_checkpoint(task_dir)
    pending = checkpoint.get("pending_confirmation") if checkpoint else None
    if not pending or pending.get("tool_call_id") != dto.toolCallId:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "NO_PENDING_APPROVAL",
                    "message": "无此待确认调用",
                }
            },
        )

    await registry.remove(task_id, dto.toolCallId)
    asyncio.create_task(
        resume_use_case.loop_runner.resume_from_snapshot(
            task=task,
            task_dir=task_dir,
            approval={"tool_call_id": dto.toolCallId, "decision": dto.decision},
            send_message_use_case=resume_use_case,
        )
    )

    return {
        "message": "approval submitted",
        "task_id": task_id,
        "tool_call_id": dto.toolCallId,
        "decision": dto.decision,
    }
