"""基础设施层 - 提供商注册表"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from src.domain.entities.llm import LLMConfig, LLMProvider
from src.infrastructure.llm.providers.base import ProviderAdapter

if TYPE_CHECKING:
    from src.infrastructure.llm.config import LLMSettings


class ProviderRegistry:
    """提供商注册表（单例）

    管理和查找 LLM 提供商适配器。
    """

    _instance: Optional["ProviderRegistry"] = None

    def __init__(self):
        self._providers: list[ProviderAdapter] = []

    @classmethod
    def get_instance(cls) -> "ProviderRegistry":
        """获取单例实例"""
        if cls._instance is None:
            from src.infrastructure.llm.config import LLMSettings

            cls._instance = cls()
            settings = LLMSettings()
            cls._instance._register_defaults(settings)
        return cls._instance

    def _register_defaults(self, settings: "LLMSettings") -> None:
        """注册默认提供商适配器"""
        from src.infrastructure.llm.providers.openai_provider import OpenAICompatibleProvider
        from src.infrastructure.llm.providers.anthropic_provider import AnthropicProvider

        self.register(OpenAICompatibleProvider(settings))
        self.register(AnthropicProvider(settings))

    def register(self, adapter: ProviderAdapter) -> None:
        """注册提供商适配器"""
        self._providers.append(adapter)

    def get_adapter(self, config: LLMConfig) -> ProviderAdapter:
        """获取提供商适配器

        Args:
            config: LLM 配置

        Returns:
            提供商适配器实例

        Raises:
            LLMProviderNotSupportedError: 当没有适配器支持该提供商时
        """
        from src.domain.exceptions import LLMProviderNotSupportedError

        for adapter in self._providers:
            if adapter.supports(config.provider):
                return adapter

        raise LLMProviderNotSupportedError(f"不支持的 LLM 提供商: {config.provider}")

    def list_available_providers(self) -> list[str]:
        """列出所有可用的提供商"""
        return [p.value for p in LLMProvider]
