"""表现层 - Session 路由"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from src.application.dtos.session_dto import (
    CreateSessionDTO,
    SendMessageDTO,
    SendMessageResponseDTO,
    SessionDetailResponseDTO,
    SessionListResponseDTO,
    SessionMessageResponseDTO,
    SessionResponseDTO,
    UpdateSessionDTO,
)
from src.application.agent_loop.session_management import SessionManagementUseCase
from src.domain.aggregates.session.session import Session
from src.domain.aggregates.session.session_message import SessionMessage
from src.domain.repositories.agent_repository import IAgentRepository
from src.domain.repositories.session_message_repository import (
    ISessionMessageRepository,
)
from src.domain.repositories.session_repository import ISessionRepository
from src.presentation.dependencies import (
    get_agent_repository,
    get_session_message_repository,
    get_session_repository,
    get_send_message_use_case,
)

router = APIRouter(prefix="/api/agents/{agent_id}/sessions", tags=["sessions"])


def _to_session_response(session: Session) -> SessionResponseDTO:
    return SessionResponseDTO(
        id=session.id,
        agent_id=session.agent_id,
        title=session.title,
        status=session.status.value,
        message_count=session.message_count,
        last_message_preview=session.last_message_preview,
        created_at=session.created_at.isoformat(),
        updated_at=session.updated_at.isoformat() if session.updated_at else None,
    )


def _to_message_response(msg: SessionMessage) -> SessionMessageResponseDTO:
    return SessionMessageResponseDTO(
        id=msg.id,
        session_id=msg.session_id,
        task_id=msg.task_id,
        role=msg.role.value,
        content=msg.content,
        thinking_content=msg.thinking_content,
        has_thinking=msg.has_thinking,
        tool_calls=msg.tool_calls,
        tool_results=msg.tool_results,
        status=msg.status.value,
        error=msg.error,
        cost=msg.cost,
        created_at=msg.created_at.isoformat(),
    )


@router.post(
    "",
    response_model=SessionResponseDTO,
    status_code=status.HTTP_201_CREATED,
    summary="创建会话",
)
async def create_session(
    agent_id: str,
    dto: CreateSessionDTO,
    agent_repo: IAgentRepository = Depends(get_agent_repository),
    session_repo: ISessionRepository = Depends(get_session_repository),
    message_repo: ISessionMessageRepository = Depends(
        get_session_message_repository),
):
    # 验证 Agent 存在
    agent = await agent_repo.get_by_id(agent_id)
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {"code": "AGENT_NOT_FOUND", "message": f"Agent '{agent_id}' not found"}
            },
        )

    use_case = SessionManagementUseCase(session_repo, message_repo)
    session = await use_case.create_session(agent_id, dto.title)
    return _to_session_response(session)


@router.get(
    "",
    response_model=SessionListResponseDTO,
    summary="会话列表",
)
async def list_sessions(
    agent_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session_repo: ISessionRepository = Depends(get_session_repository),
    message_repo: ISessionMessageRepository = Depends(
        get_session_message_repository),
):
    use_case = SessionManagementUseCase(session_repo, message_repo)
    offset = (page - 1) * page_size
    sessions = await use_case.list_sessions(agent_id, limit=page_size, offset=offset)
    return SessionListResponseDTO(
        data=[_to_session_response(s) for s in sessions],
        total=len(sessions),
    )


@router.get(
    "/{session_id}",
    response_model=SessionDetailResponseDTO,
    summary="会话详情（含消息）",
)
async def get_session(
    agent_id: str,
    session_id: str,
    session_repo: ISessionRepository = Depends(get_session_repository),
    message_repo: ISessionMessageRepository = Depends(
        get_session_message_repository),
):
    session = await session_repo.get_by_id(session_id)
    if not session or session.agent_id != agent_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "SESSION_NOT_FOUND"}},
        )

    messages = await message_repo.list_by_session(session_id)
    return SessionDetailResponseDTO(
        session=_to_session_response(session),
        messages=[_to_message_response(m) for m in messages],
    )


@router.patch(
    "/{session_id}",
    response_model=SessionResponseDTO,
    summary="更新会话",
)
async def update_session(
    agent_id: str,
    session_id: str,
    dto: UpdateSessionDTO,
    session_repo: ISessionRepository = Depends(get_session_repository),
    message_repo: ISessionMessageRepository = Depends(
        get_session_message_repository),
):
    session = await session_repo.get_by_id(session_id)
    if not session or session.agent_id != agent_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "SESSION_NOT_FOUND"}},
        )

    use_case = SessionManagementUseCase(session_repo, message_repo)
    updated = await use_case.update_session(session_id, dto.title, dto.status)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return _to_session_response(updated)


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除会话",
)
async def delete_session(
    agent_id: str,
    session_id: str,
    session_repo: ISessionRepository = Depends(get_session_repository),
    message_repo: ISessionMessageRepository = Depends(
        get_session_message_repository),
):
    session = await session_repo.get_by_id(session_id)
    if not session or session.agent_id != agent_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "SESSION_NOT_FOUND"}},
        )

    use_case = SessionManagementUseCase(session_repo, message_repo)
    await use_case.delete_session(session_id)


@router.post(
    "/{session_id}/messages",
    response_model=SendMessageResponseDTO,
    status_code=status.HTTP_202_ACCEPTED,
    summary="发送消息（触发 Agent Loop 执行）",
)
async def send_message(
    agent_id: str,
    session_id: str,
    dto: SendMessageDTO,
    request: Request,
    agent_repo: IAgentRepository = Depends(get_agent_repository),
    session_repo: ISessionRepository = Depends(get_session_repository),
    send_message_uc=Depends(get_send_message_use_case),
):
    """发送消息并触发 Agent Loop 执行。

    返回 202 + taskId，前端通过 SSE 订阅任务事件。
    """
    # 验证 Agent 存在
    agent = await agent_repo.get_by_id(agent_id)
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "AGENT_NOT_FOUND"}},
        )

    # 验证 Session 存在
    session = await session_repo.get_by_id(session_id)
    if not session or session.agent_id != agent_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "SESSION_NOT_FOUND"}},
        )

    result = await send_message_uc.execute(
        agent_id=agent_id,
        session_id=session_id,
        content=dto.content,
        model=dto.model,
        max_turns=dto.max_turns or 100,
        workspace=dto.workspace or "/tmp/agent-workspace",
        skill_ids=dto.skill_ids,
    )

    # 将 asyncio.Task 存储到 app.state.running_tasks 以支持 cancel
    asyncio_task = result.get("asyncio_task")
    task_id = result["task_id"]
    if asyncio_task is not None:
        running_tasks: dict = request.app.state.running_tasks
        running_tasks[task_id] = asyncio_task
        asyncio_task.add_done_callback(
            lambda _: running_tasks.pop(task_id, None))

    return SendMessageResponseDTO(
        user_message=_to_message_response(result["user_message"]),
        task_id=task_id,
    )
