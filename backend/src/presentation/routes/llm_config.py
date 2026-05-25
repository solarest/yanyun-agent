"""表现层 - LLM 配置管理路由"""

from fastapi import APIRouter, Depends

from src.application.dtos.llm_dto import LLMProviderInfoDTO
from src.domain.value_objects.llm_config import LLMProvider
from src.presentation.dependencies import get_llm_settings
from src.infrastructure.llm.config import LLMSettings

router = APIRouter(prefix="/api/llm", tags=["LLM 配置"])


def _get_models_for_provider(provider: LLMProvider) -> list[str]:
    """获取提供商的可用模型列表"""
    models = {
        LLMProvider.OPENAI: ["gpt-4", "gpt-4-turbo", "gpt-3.5-turbo", "gpt-4o", "gpt-4o-mini"],
        LLMProvider.ANTHROPIC: [
            "claude-3-opus",
            "claude-3-sonnet",
            "claude-3-haiku",
            "claude-3-5-sonnet",
        ],
        LLMProvider.OLLAMA: ["llama3", "mistral", "phi3"],
        LLMProvider.GROQ: ["llama3-70b-8192", "llama3-8b-8192"],
        LLMProvider.DEEPSEEK: ["deepseek-chat"],
        LLMProvider.QWEN: ["qwen-turbo", "qwen-plus", "qwen-max"],
        LLMProvider.ZHIPU: ["glm-4", "glm-3-turbo"],
    }
    return models.get(provider, [])


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
                available_models=_get_models_for_provider(provider),
            )
        )
    return providers
