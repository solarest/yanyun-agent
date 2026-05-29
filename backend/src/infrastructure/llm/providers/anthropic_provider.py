"""基础设施层 - Anthropic 提供商"""

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel

from src.domain.value_objects.llm_config import LLMConfig, LLMProvider
from src.infrastructure.llm.providers.base import ProviderAdapter
from src.infrastructure.llm.config import LLMSettings


ANTHROPIC_PRICING = {
    "claude-3-opus": (0.015, 0.075),
    "claude-3-sonnet": (0.003, 0.015),
    "claude-3-haiku": (0.00025, 0.00125),
    "claude-3-5-sonnet": (0.003, 0.015),
}


class AnthropicProvider(ProviderAdapter):
    """Anthropic (Claude) 提供商"""

    def __init__(self, settings: LLMSettings):
        self.settings = settings

    def supports(self, provider: LLMProvider) -> bool:
        return provider == LLMProvider.ANTHROPIC

    def create_model(self, config: LLMConfig) -> BaseChatModel:
        kwargs = {
            "model": config.model,
            "temperature": config.temperature,
            "max_retries": config.max_retries,
        }

        if config.max_tokens:
            kwargs["max_tokens"] = config.max_tokens

        if config.api_key:
            kwargs["anthropic_api_key"] = config.api_key
        elif self.settings.anthropic_api_key:
            kwargs["anthropic_api_key"] = self.settings.anthropic_api_key.get_secret_value()

        if config.api_base:
            kwargs["anthropic_api_url"] = config.api_base

        kwargs.update(config.extra)

        return ChatAnthropic(**kwargs)

    def get_model_pricing(self, model: str) -> tuple[float, float]:
        for key, price in ANTHROPIC_PRICING.items():
            if model.startswith(key):
                return price
        return (0.0, 0.0)
