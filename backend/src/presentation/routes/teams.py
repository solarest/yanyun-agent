"""表现层 - Team CRUD 与执行路由"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from src.domain.team.entity import Team
from src.application.team.dto import (
    CreateTeamDTO,
    UpdateTeamDTO,
    ExecuteTeamDTO,
    TeamResponseDTO,
    TeamDetailDTO,
    TeamMemberDTO,
    TeamListResponseDTO,
    ExecuteTeamResponseDTO,
)
from src.application.team.management import (
    TeamManagementUseCase,
    TeamNotFoundError,
    DuplicateTeamNameError,
    AgentNotFoundError,
)
from src.presentation.dependencies import (
    get_team_management_use_case,
)

router = APIRouter(prefix="/api/teams", tags=["teams"])

# ── Helpers ──────────────────────────────────────────────


def _to_team_response(team: Team, member_count: int = 0) -> TeamResponseDTO:
    return TeamResponseDTO(
        id=team.id,
        name=team.name,
        description=team.description,
        leader_id=team.leader_id,
        goal=team.goal,
        status=team.status.value if hasattr(team.status, 'value') else team.status,
        config=team.config,
        member_count=member_count,
        created_at=team.created_at.isoformat() if team.created_at else "",
        updated_at=team.updated_at.isoformat() if team.updated_at else None,
    )


async def _to_team_detail(
    team: Team,
    mgmt: TeamManagementUseCase,
) -> TeamDetailDTO:
    members = await mgmt.list_members(team.id)
    # 查询所有成员的 agent 名称
    agent_names: dict[str, str] = {}
    for m in members:
        agent = await mgmt._agent_repo.get_by_id(m.agent_id)
        if agent:
            agent_names[m.agent_id] = agent.name
    member_dtos = [
        TeamMemberDTO(
            id=m.id,
            agent_id=m.agent_id,
            agent_name=agent_names.get(m.agent_id, ""),
            role=m.role.value if hasattr(m.role, 'value') else m.role,
            status=m.status,
            joined_at=m.joined_at.isoformat() if m.joined_at else "",
        )
        for m in members
    ]
    return TeamDetailDTO(
        id=team.id,
        name=team.name,
        description=team.description,
        leader_id=team.leader_id,
        goal=team.goal,
        status=team.status.value if hasattr(team.status, 'value') else team.status,
        config=team.config,
        member_count=len(members),
        created_at=team.created_at.isoformat() if team.created_at else "",
        updated_at=team.updated_at.isoformat() if team.updated_at else None,
        members=member_dtos,
    )


# ── Routes ────────────────────────────────────────────────


@router.post("", response_model=TeamResponseDTO, status_code=201)
async def create_team(
    dto: CreateTeamDTO,
    mgmt: TeamManagementUseCase = Depends(get_team_management_use_case),
) -> TeamResponseDTO:
    """创建团队"""
    try:
        team = await mgmt.create(
            name=dto.name,
            description=dto.description,
            leader_id=dto.leader_id,
            member_ids=dto.member_ids,
        )
        members = await mgmt.list_members(team.id)
        return _to_team_response(team, len(members))
    except DuplicateTeamNameError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except AgentNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=TeamListResponseDTO)
async def list_teams(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    mgmt: TeamManagementUseCase = Depends(get_team_management_use_case),
) -> TeamListResponseDTO:
    """获取团队列表"""
    teams, total = await mgmt.list_all(page=page, page_size=page_size)
    team_dtos = []
    for team in teams:
        members = await mgmt.list_members(team.id)
        team_dtos.append(_to_team_response(team, len(members)))
    return TeamListResponseDTO(
        teams=team_dtos,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{team_id}", response_model=TeamDetailDTO)
async def get_team(
    team_id: str,
    mgmt: TeamManagementUseCase = Depends(get_team_management_use_case),
) -> TeamDetailDTO:
    """获取团队详情"""
    team = await mgmt.get_by_id(team_id)
    if team is None:
        raise HTTPException(status_code=404, detail=f"Team '{team_id}' not found")
    return await _to_team_detail(team, mgmt)


@router.put("/{team_id}", response_model=TeamResponseDTO)
async def update_team(
    team_id: str,
    dto: UpdateTeamDTO,
    mgmt: TeamManagementUseCase = Depends(get_team_management_use_case),
) -> TeamResponseDTO:
    """更新团队"""
    try:
        team = await mgmt.update(
            team_id=team_id,
            name=dto.name,
            description=dto.description,
            leader_id=dto.leader_id,
            member_ids=dto.member_ids,
        )
        members = await mgmt.list_members(team.id)
        return _to_team_response(team, len(members))
    except TeamNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DuplicateTeamNameError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.delete("/{team_id}", status_code=204)
async def delete_team(
    team_id: str,
    mgmt: TeamManagementUseCase = Depends(get_team_management_use_case),
) -> None:
    """删除团队"""
    try:
        await mgmt.delete(team_id)
    except TeamNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{team_id}/members", response_model=list[TeamMemberDTO])
async def list_team_members(
    team_id: str,
    mgmt: TeamManagementUseCase = Depends(get_team_management_use_case),
) -> list[TeamMemberDTO]:
    """获取团队成员列表"""
    try:
        members = await mgmt.list_members(team_id)
    except TeamNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # 查询所有成员的 agent 名称
    agent_names: dict[str, str] = {}
    for m in members:
        agent = await mgmt._agent_repo.get_by_id(m.agent_id)
        if agent:
            agent_names[m.agent_id] = agent.name

    return [
        TeamMemberDTO(
            id=m.id,
            agent_id=m.agent_id,
            agent_name=agent_names.get(m.agent_id, ""),
            role=m.role.value if hasattr(m.role, 'value') else m.role,
            status=m.status,
            joined_at=m.joined_at.isoformat() if m.joined_at else "",
        )
        for m in members
    ]


@router.post("/{team_id}/execute", response_model=ExecuteTeamResponseDTO, status_code=202)
async def execute_team(
    team_id: str,
    dto: ExecuteTeamDTO,
    request: Request,
    mgmt: TeamManagementUseCase = Depends(get_team_management_use_case),
) -> ExecuteTeamResponseDTO:
    """执行团队目标（异步）"""
    team = await mgmt.get_by_id(team_id)
    if team is None:
        raise HTTPException(status_code=404, detail=f"Team '{team_id}' not found")

    import asyncio
    from src.presentation.dependencies import get_team_execution_use_case

    # 获取 execution use case（需要 request 上下文）
    execution_uc = get_team_execution_use_case(request)

    # 预生成 execution_id（也是 leader 的 task_id），前端用它连接 SSE
    import uuid
    execution_id = f"team-{uuid.uuid4().hex[:12]}"

    # 后台异步执行
    asyncio.create_task(
        execution_uc.execute(
            team_id=team_id,
            goal=dto.goal,
            model=dto.model,
            max_turns=dto.max_turns,
            workspace=dto.workspace,
            execution_id=execution_id,
        )
    )

    return ExecuteTeamResponseDTO(
        team_id=team_id,
        execution_id=execution_id,
        workspace=dto.workspace,
        status="started",
        message=f"Team '{team.name}' execution started. Stream: /api/tasks/{execution_id}/stream",
    )


@router.get("/{team_id}/workspace-files")
async def list_workspace_files(
    team_id: str,
    path: str = Query(default="/tmp/team-workspace"),
    mgmt: TeamManagementUseCase = Depends(get_team_management_use_case),
):
    """列出工作空间下的文件"""
    import os
    from fastapi import HTTPException as FastAPIHTTPException

    team = await mgmt.get_by_id(team_id)
    if team is None:
        raise FastAPIHTTPException(status_code=404, detail=f"Team '{team_id}' not found")

    workspace = path
    if not os.path.isdir(workspace):
        return {"files": [], "workspace": workspace}

    files = []
    try:
        for entry in sorted(os.scandir(workspace), key=lambda e: e.name):
            if entry.name.startswith('.'):
                continue
            stat = entry.stat()
            files.append({
                "name": entry.name,
                "path": entry.path,
                "is_dir": entry.is_dir(),
                "size": stat.st_size if entry.is_file() else 0,
                "modified_at": stat.st_mtime,
            })
    except PermissionError:
        pass

    return {"files": files, "workspace": workspace}
