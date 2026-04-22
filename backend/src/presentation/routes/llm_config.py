"""表现层 - LLM 配置管理路由"""
from fastapi import APIRouter, Depends

from src.application.use_cases.create_llm_use_case import CreateLLMUseCase
from src.presentation.dependencies import get_llm_use_case

router = APIRouter(prefix="/api/llm", tags=["LLM 配置"])


@router.get("/providers")
async def list_providers(
    use_case: CreateLLMUseCase = Depends(get_llm_use_case),
):
    """列出可用 LLM 提供商"""
    return use_case.list_providers()
