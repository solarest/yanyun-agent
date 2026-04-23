"""表现层 - 任务 CRUD 路由"""

from fastapi import APIRouter, Depends, HTTPException, status

from src.application.dtos.task_dto import CreateTaskDTO, TaskListResponseDTO, TaskResponseDTO
from src.domain.entities.task import Task, TaskConfig, TaskStatus
from src.domain.repositories.agent_repository import IAgentRepository
from src.domain.repositories.task_repository import ITaskRepository
from src.presentation.dependencies import get_agent_repository, get_task_repository

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
    task_repo: ITaskRepository = Depends(get_task_repository),
    agent_repo: IAgentRepository = Depends(get_agent_repository),
):
    """创建任务

    创建任务实体并保存到数据库。
    如果指定了 agent_id，会校验 Agent 是否存在。
    任务创建后处于 idle 状态，等待执行。
    """
    # 如果指定了 agent_id，校验 Agent 是否存在
    if dto.agent_id is not None:
        agent = await agent_repo.get_by_id(dto.agent_id)
        if agent is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "error": {
                        "code": "AGENT_NOT_FOUND",
                        "message": f"Agent '{dto.agent_id}' 不存在",
                    }
                },
            )

    task = Task(
        message=dto.message,
        workspace=dto.workspace,
        status=TaskStatus.IDLE,
        model=dto.model or "gpt-4",
        config=TaskConfig(max_turns=dto.max_turns or 100),
        agent_id=dto.agent_id,
    )

    task = await task_repo.add(task)

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
