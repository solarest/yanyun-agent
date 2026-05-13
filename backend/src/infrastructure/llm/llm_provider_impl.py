"""基础设施层 - LLM Provider 实现

实现领域层的 ILLMProvider 接口。
"""

from typing import Optional

from langchain_core.language_models import BaseChatModel

from src.domain.interfaces.llm_provider import ILLMProvider
from src.infrastructure.llm.model_factory import create_chat_model as _create_chat_model


class LLMProviderImpl(ILLMProvider):
    """LLM 提供商实现

    职责：
    - 实现 ILLMProvider 接口
    - 委托给现有的 create_chat_model 工厂函数
    - 保持向后兼容性
    """

    def create_chat_model(
        self,
        model: Optional[str] = None,
        temperature: float = 0.7,
        provider: Optional[str] = None,
    ) -> BaseChatModel:
        """创建 ChatModel 实例

        委托给基础设施层的工厂函数。
        """
        return _create_chat_model(
            model=model,
            temperature=temperature,
            provider=provider,
        )
