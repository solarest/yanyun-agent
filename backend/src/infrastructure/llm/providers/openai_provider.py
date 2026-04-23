"""基础设施层 - OpenAI 兼容提供商"""

from typing import Optional

from langchain_openai import ChatOpenAI
from langchain_core.language_models import BaseChatModel

from src.domain.entities.llm import LLMConfig, LLMProvider
from src.infrastructure.llm.providers.base import ProviderAdapter
from src.infrastructure.llm.config import LLMSettings


# 模型定价表（每 1K tokens，美元）
OPENAI_COMPATIBLE_PRICING = {
    "gpt-4": (0.03, 0.06),
    "gpt-4-turbo": (0.01, 0.03),
    "gpt-3.5-turbo": (0.0005, 0.0015),
    "gpt-4o": (0.005, 0.015),
    "gpt-4o-mini": (0.00015, 0.0006),
    # Groq
    "llama3-70b-8192": (0.00059, 0.00079),
    "llama3-8b-8192": (0.00005, 0.00008),
    # DeepSeek
    "deepseek-chat": (0.00014, 0.00028),
    # 通义千问
    "qwen-turbo": (0.00028, 0.00083),
    "qwen-plus": (0.00056, 0.00166),
    "qwen-max": (0.0028, 0.0083),
    # 智谱
    "glm-4": (0.01, 0.01),
    "glm-3-turbo": (0.001, 0.001),
}


class OpenAICompatibleProvider(ProviderAdapter):
    """OpenAI 兼容提供商

    支持: OpenAI、Azure OpenAI、Ollama、Groq、DeepSeek、通义千问、智谱
    """

    SUPPORTED_PROVIDERS = {
        LLMProvider.OPENAI,
        LLMProvider.AZURE_OPENAI,
        LLMProvider.OLLAMA,
        LLMProvider.GROQ,
        LLMProvider.DEEPSEEK,
        LLMProvider.QWEN,
        LLMProvider.ZHIPU,
    }

    def __init__(self, settings: LLMSettings):
        self.settings = settings

    def supports(self, provider: LLMProvider) -> bool:
        return provider in self.SUPPORTED_PROVIDERS

    def create_model(self, config: LLMConfig) -> BaseChatModel:
        base_url = config.api_base or self._get_base_url(config.provider)
        api_key = config.api_key or self._get_api_key(config.provider)

        kwargs = {
            "model": config.model,
            "temperature": config.temperature,
            "timeout": config.timeout,
            "max_retries": config.max_retries,
        }

        if config.max_tokens:
            kwargs["max_tokens"] = config.max_tokens

        if base_url:
            kwargs["base_url"] = base_url

        if api_key:
            kwargs["api_key"] = api_key

        # 合并 extra 参数
        kwargs.update(config.extra)

        return ChatOpenAI(**kwargs)

    def get_model_pricing(self, model: str) -> tuple[float, float]:
        # 精确匹配
        if model in OPENAI_COMPATIBLE_PRICING:
            return OPENAI_COMPATIBLE_PRICING[model]

        # 前缀匹配
        for key, price in OPENAI_COMPATIBLE_PRICING.items():
            if model.startswith(key):
                return price

        # 未知模型，返回 0
        return (0.0, 0.0)

    def _get_base_url(self, provider: LLMProvider) -> Optional[str]:
        urls = {
            LLMProvider.OPENAI: self.settings.openai_api_base,
            LLMProvider.OLLAMA: f"{self.settings.ollama_base_url}/v1",
            LLMProvider.GROQ: "https://api.groq.com/openai/v1",
            LLMProvider.DEEPSEEK: "https://api.deepseek.com/v1",
            LLMProvider.QWEN: "https://dashscope.aliyuncs.com/compatible-mode/v1",
            LLMProvider.ZHIPU: "https://open.bigmodel.cn/api/paas/v4",
        }
        return urls.get(provider)

    def _get_api_key(self, provider: LLMProvider) -> Optional[str]:
        keys = {
            LLMProvider.OPENAI: self.settings.openai_api_key,
            LLMProvider.GROQ: self.settings.groq_api_key,
            LLMProvider.DEEPSEEK: self.settings.deepseek_api_key,
            LLMProvider.QWEN: self.settings.dashscope_api_key,
            LLMProvider.ZHIPU: self.settings.zhipu_api_key,
        }
        secret = keys.get(provider)
        return secret.get_secret_value() if secret else None
