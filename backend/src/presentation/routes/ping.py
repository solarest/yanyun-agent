"""表现层 - Ping 路由"""

from fastapi import APIRouter, Depends
from src.application.use_cases.ping_use_case import PingUseCase
from src.application.dtos.ping_dto import PingRequest, PingResponse
from src.presentation.dependencies import get_ping_use_case

router = APIRouter(prefix="/api", tags=["ping"])


@router.post("/ping", response_model=PingResponse)
async def ping(request: PingRequest, use_case: PingUseCase = Depends(get_ping_use_case)):
    """Ping 接口 - 演示 DDD 架构的完整流程

    流程:
    1. FastAPI 接收请求并验证 DTO
    2. 注入 PingUseCase
    3. UseCase 编排业务逻辑
    4. 返回响应 DTO
    """
    return use_case.execute(request)
