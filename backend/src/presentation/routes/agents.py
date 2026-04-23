"""表现层 - Agent CRUD 路由"""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.application.dtos.agent_dto import (
    AgentListResponseDTO,
    AgentResponseDTO,
    CreateAgentDTO,
    UpdateAgentDTO,
)
from src.application.use_cases.agent_use_cases import (
    CreateAgentUseCase,
    DeleteAgentUseCase,
    GetAgentUseCase,
    ListAgentsUseCase,
    UpdateAgentUseCase,
)
from src.domain.entities.agent import Agent
from src.domain.exceptions import AgentNotFoundError, DuplicateAgentNameError
from src.domain.repositories.agent_repository import IAgentRepository
from src.presentation.dependencies import get_agent_repository

router = APIRouter(prefix="/api/agents", tags=["agents"])


def _to_response(agent: Agent) -> AgentResponseDTO:
    """Agent 实体转响应 DTO"""
    return AgentResponseDTO(
        id=agent.id,
        name=agent.name,
        role=agent.role,
        system_prompt_template=agent.system_prompt_template,
        created_at=agent.created_at.isoformat(),
        updated_at=agent.updated_at.isoformat() if agent.updated_at else None,
    )


@router.post(
    "",
    response_model=AgentResponseDTO,
    status_code=status.HTTP_201_CREATED,
    summary="创建 Agent",
    description="创建一个新的 Agent，名称必须唯一",
    responses={
        409: {"description": "Agent 名称已存在"},
    },
)
async def create_agent(
    dto: CreateAgentDTO,
    agent_repo: IAgentRepository = Depends(get_agent_repository),
) -> AgentResponseDTO:
    """创建 Agent"""
    use_case = CreateAgentUseCase(agent_repo)
    try:
        agent = await use_case.execute(dto)
    except DuplicateAgentNameError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "DUPLICATE_AGENT_NAME", "message": str(e)}},
        )
    return _to_response(agent)


@router.get(
    "",
    response_model=AgentListResponseDTO,
    summary="获取 Agent 列表",
    description="分页获取 Agent 列表",
)
async def list_agents(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    agent_repo: IAgentRepository = Depends(get_agent_repository),
) -> AgentListResponseDTO:
    """获取 Agent 列表"""
    use_case = ListAgentsUseCase(agent_repo)
    offset = (page - 1) * page_size
    agents = await use_case.execute(limit=page_size, offset=offset)
    return AgentListResponseDTO(
        data=[_to_response(a) for a in agents],
        total=len(agents),
    )


@router.get(
    "/{agent_id}",
    response_model=AgentResponseDTO,
    summary="获取 Agent 详情",
    responses={404: {"description": "Agent 不存在"}},
)
async def get_agent(
    agent_id: str,
    agent_repo: IAgentRepository = Depends(get_agent_repository),
) -> AgentResponseDTO:
    """获取 Agent 详情"""
    use_case = GetAgentUseCase(agent_repo)
    try:
        agent = await use_case.execute(agent_id)
    except AgentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "AGENT_NOT_FOUND", "message": str(e)}},
        )
    return _to_response(agent)


@router.put(
    "/{agent_id}",
    response_model=AgentResponseDTO,
    summary="更新 Agent",
    responses={
        404: {"description": "Agent 不存在"},
        409: {"description": "Agent 名称已存在"},
    },
)
async def update_agent(
    agent_id: str,
    dto: UpdateAgentDTO,
    agent_repo: IAgentRepository = Depends(get_agent_repository),
) -> AgentResponseDTO:
    """更新 Agent（PATCH 语义，所有字段可选）"""
    use_case = UpdateAgentUseCase(agent_repo)
    try:
        agent = await use_case.execute(agent_id, dto)
    except AgentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "AGENT_NOT_FOUND", "message": str(e)}},
        )
    except DuplicateAgentNameError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": {"code": "DUPLICATE_AGENT_NAME", "message": str(e)}},
        )
    return _to_response(agent)


@router.delete(
    "/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除 Agent",
    responses={404: {"description": "Agent 不存在"}},
)
async def delete_agent(
    agent_id: str,
    agent_repo: IAgentRepository = Depends(get_agent_repository),
) -> None:
    """删除 Agent"""
    use_case = DeleteAgentUseCase(agent_repo)
    try:
        await use_case.execute(agent_id)
    except AgentNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "AGENT_NOT_FOUND", "message": str(e)}},
        )
