"""表现层 - Ping 路由"""

from datetime import datetime
from fastapi import APIRouter, Depends
from src.application.dtos.ping_dto import PingRequest, PingResponse
from src.domain.repositories.base import Repository
from src.domain.entities.base import Entity
from src.presentation.dependencies import get_repository

router = APIRouter(prefix="/api", tags=["ping"])


@router.post("/ping", response_model=PingResponse)
async def ping(
    request: PingRequest,
    repository: Repository[Entity] = Depends(get_repository),
) -> PingResponse:
    """Ping 接口 - 健康检查"""
    entities = repository.list_all()
    entity_count = len(entities)
    
    return PingResponse(
        status="ok",
        timestamp=datetime.now(),
        message=f"{request.message} - entity count: {entity_count}",
        server="ddd-python-backend",
    )
