"""表现层 - LLM 配置管理路由"""

from fastapi import APIRouter, Depends

from src.application.dtos.llm_dto import LLMProviderInfoDTO
from src.domain.agent_loop.llm_config import LLMProvider, LLM_PROVIDER_MODELS
from src.presentation.dependencies import get_llm_settings
from src.infrastructure.llm.config import LLMSettings

router = APIRouter(prefix="/api/llm", tags=["LLM 配置"])


@router.get("/providers")
async def list_providers(
    settings: LLMSettings = Depends(get_llm_settings),
) -> list[LLMProviderInfoDTO]:
    """列出可用 LLM 提供商"""
    providers = []
    for provider in LLMProvider:
        providers.append(
            LLMProviderInfoDTO(
                name=provider.value,
                available_models=LLM_PROVIDER_MODELS.get(provider, []),
            )
        )
    return providers
