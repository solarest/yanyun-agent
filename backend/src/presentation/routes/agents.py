"""表现层 - Agent CRUD 路由"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from src.application.agent.management import (
    AgentManagementUseCase,
    AgentNotFoundError,
    DuplicateAgentNameError,
)
from src.application.dtos.agent_dto import (
    AgentConfigResponseDTO,
    AgentListResponseDTO,
    AgentResponseDTO,
    CreateAgentDTO,
    UpdateAgentConfigDTO,
    UpdateAgentDTO,
)
from src.domain.agent.entity import Agent
from src.domain.entities.tool import ToolDef
from src.infrastructure.tools.registry import ToolRegistry
from src.presentation.dependencies import (
    create_tool_registry,
    get_agent_use_case,
)

router = APIRouter(prefix="/api/agents", tags=["agents"])


# === Tool 相关 DTO ===


class ToolDefResponse(BaseModel):
    """工具定义响应 DTO"""

    name: str = Field(..., description="工具名称")
    description: str = Field(..., description="工具描述")
    category: str = Field(default="general", description="工具分类")
    parameters: list[dict] = Field(default_factory=list, description="参数定义")
    returns: str = Field(default="", description="返回值描述")

    @classmethod
    def from_tool_def(cls, tool_def: ToolDef) -> "ToolDefResponse":
        return cls(
            name=tool_def.name,
            description=tool_def.description,
            category=tool_def.category,
            parameters=[
                {
                    "name": p.name,
                    "type": p.type,
                    "description": p.description,
                    "required": p.required,
                    "enum": p.enum,
                }
                for p in tool_def.parameters
            ],
            returns=tool_def.returns,
        )


class ToolListResponse(BaseModel):
    """工具列表响应 DTO"""

    tools: list[ToolDefResponse] = Field(..., description="工具列表")
    total: int = Field(..., description="工具总数")


# === Agent CRUD 路由 ===


def _to_response(agent: Agent) -> AgentResponseDTO:
    """Agent 实体转响应 DTO"""
    return AgentResponseDTO(
        id=agent.id,
        name=agent.name,
        description=agent.description,
        vibes=agent.get_vibes(),
        identity_md=agent.identity_md,
        soul_md=agent.soul_md,
        agents_md=agent.agents_md,
        bootstrap_md=agent.bootstrap_md,
        memory_md=agent.memory_md,
        tools_md=agent.tools_md,
        user_md=agent.user_md,
        config_version=agent.config_version,
        created_at=agent.created_at.isoformat(),
        updated_at=agent.updated_at.isoformat() if agent.updated_at else None,
    )


def _to_config_response(agent: Agent) -> AgentConfigResponseDTO:
    """Agent 实体转配置响应 DTO"""
    return AgentConfigResponseDTO(
        identity_md=agent.identity_md,
        soul_md=agent.soul_md,
        agents_md=agent.agents_md,
        bootstrap_md=agent.bootstrap_md,
        memory_md=agent.memory_md,
        tools_md=agent.tools_md,
        user_md=agent.user_md,
        config_version=agent.config_version,
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
    agent_uc: AgentManagementUseCase = Depends(get_agent_use_case),
) -> AgentResponseDTO:
    """创建 Agent"""
    try:
        agent = await agent_uc.create(
            name=dto.name,
            description=dto.description,
            vibes=dto.vibes,
            identity_md=dto.identity_md or "",
            soul_md=dto.soul_md or "",
            agents_md=dto.agents_md or "",
            bootstrap_md=dto.bootstrap_md or "",
            memory_md=dto.memory_md or "",
            tools_md=dto.tools_md or "",
            user_md=dto.user_md or "",
        )
    except DuplicateAgentNameError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "DUPLICATE_AGENT_NAME",
                    "message": f"Agent 名称 '{dto.name}' 已存在",
                }
            },
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
    agent_uc: AgentManagementUseCase = Depends(get_agent_use_case),
) -> AgentListResponseDTO:
    """获取 Agent 列表"""
    agents = await agent_uc.list_all(page=page, page_size=page_size)
    return AgentListResponseDTO(
        data=[_to_response(a) for a in agents],
        total=len(agents),
    )


@router.get(
    "/tools",
    response_model=ToolListResponse,
    summary="获取已注册工具列表",
    description="获取所有已注册的工具定义，用于创建 Agent 时选择工具",
)
async def list_tools(
    category: Optional[str] = Query(None, description="按分类筛选工具"),
    tool_registry: ToolRegistry = Depends(create_tool_registry),
) -> ToolListResponse:
    """获取已注册工具列表"""
    tool_defs = tool_registry.get_tool_defs(category=category)
    return ToolListResponse(
        tools=[ToolDefResponse.from_tool_def(td) for td in tool_defs],
        total=len(tool_defs),
    )


@router.get(
    "/{agent_id}",
    response_model=AgentResponseDTO,
    summary="获取 Agent 详情",
    responses={404: {"description": "Agent 不存在"}},
)
async def get_agent(
    agent_id: str,
    agent_uc: AgentManagementUseCase = Depends(get_agent_use_case),
) -> AgentResponseDTO:
    """获取 Agent 详情"""
    agent = await agent_uc.get_by_id(agent_id)
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "AGENT_NOT_FOUND",
                    "message": f"Agent '{agent_id}' 不存在",
                }
            },
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
    agent_uc: AgentManagementUseCase = Depends(get_agent_use_case),
) -> AgentResponseDTO:
    """更新 Agent（PATCH 语义，所有字段可选）"""
    # 收集配置文件字段
    config_fields = {}
    for field_name in [
        "identity_md",
        "soul_md",
        "agents_md",
        "bootstrap_md",
        "memory_md",
        "tools_md",
        "user_md",
    ]:
        value = getattr(dto, field_name)
        if value is not None:
            config_fields[field_name] = value

    try:
        agent = await agent_uc.update(
            agent_id=agent_id,
            name=dto.name,
            description=dto.description,
            vibes=dto.vibes,
            **config_fields,
        )
    except AgentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "AGENT_NOT_FOUND",
                    "message": f"Agent '{agent_id}' 不存在",
                }
            },
        )
    except DuplicateAgentNameError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "DUPLICATE_AGENT_NAME",
                    "message": f"Agent 名称 '{dto.name}' 已存在",
                }
            },
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
    agent_uc: AgentManagementUseCase = Depends(get_agent_use_case),
) -> None:
    """删除 Agent"""
    try:
        await agent_uc.delete(agent_id)
    except AgentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "AGENT_NOT_FOUND",
                    "message": f"Agent '{agent_id}' 不存在",
                }
            },
        )


@router.get(
    "/{agent_id}/config",
    response_model=AgentConfigResponseDTO,
    summary="获取 Agent 配置文件",
    responses={404: {"description": "Agent 不存在"}},
)
async def get_agent_config(
    agent_id: str,
    agent_uc: AgentManagementUseCase = Depends(get_agent_use_case),
) -> AgentConfigResponseDTO:
    """获取 Agent 的七个配置文件内容"""
    agent = await agent_uc.get_by_id(agent_id)
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "AGENT_NOT_FOUND",
                    "message": f"Agent '{agent_id}' 不存在",
                }
            },
        )
    return _to_config_response(agent)


@router.put(
    "/{agent_id}/config",
    response_model=AgentConfigResponseDTO,
    summary="更新 Agent 配置文件",
    responses={404: {"description": "Agent 不存在"}},
)
async def update_agent_config(
    agent_id: str,
    dto: UpdateAgentConfigDTO,
    agent_uc: AgentManagementUseCase = Depends(get_agent_use_case),
) -> AgentConfigResponseDTO:
    """部分更新 Agent 配置文件，自动递增版本号"""
    config_fields = {k: v for k, v in dto.model_dump().items() if v is not None}

    try:
        agent = await agent_uc.update_config(agent_id, config_fields)
    except AgentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "AGENT_NOT_FOUND",
                    "message": f"Agent '{agent_id}' 不存在",
                }
            },
        )
    return _to_config_response(agent)
