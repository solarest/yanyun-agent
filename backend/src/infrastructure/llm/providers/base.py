"""基础设施层 - 提供商适配器协议"""

from typing import Protocol

from langchain_core.language_models import BaseChatModel

from src.domain.value_objects.llm_config import LLMConfig, LLMProvider


class ProviderAdapter(Protocol):
    """提供商适配器协议

    所有 LLM 提供商必须实现此协议。
    """

    def supports(self, provider: LLMProvider) -> bool:
        """判断是否支持该提供商"""
        ...

    def create_model(self, config: LLMConfig) -> BaseChatModel:
        """创建 ChatModel 实例"""
        ...

    def get_model_pricing(self, model: str) -> tuple[float, float]:
        """获取模型定价（每 1K tokens 的价格）

        Returns:
            (prompt_price, completion_price)
        """
        ...
