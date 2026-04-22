"""基础设施层 - LangChain ChatModel 工厂（统一版本）"""

from typing import Optional

from langchain_core.language_models import BaseChatModel

from src.domain.entities.llm import LLMConfig, LLMProvider
from src.infrastructure.llm.providers.registry import ProviderRegistry
from src.infrastructure.llm.callback import LLMUsageCallbackHandler


def create_chat_model(
    model: str = "gpt-4",
    temperature: float = 0.7,
    provider: Optional[str] = None,
) -> BaseChatModel:
    """创建 ChatModel 实例（保持向后兼容）

    Args:
        model: 模型名称
        temperature: 温度参数
        provider: 提供商名称，如果为 None 则根据模型名推断

    Returns:
        LangChain ChatModel 实例（带 CallbackHandler）
    """
    # 自动推断提供商
    if provider is None:
        if "claude" in model.lower():
            provider = "anthropic"
        else:
            provider = "openai"

    config = LLMConfig(
        provider=LLMProvider(provider),
        model=model,
        temperature=temperature,
    )

    return _build_model_with_middleware(config)


def create_chat_model_with_config(config: LLMConfig) -> BaseChatModel:
    """使用完整配置创建 ChatModel 实例

    Args:
        config: LLM 配置实体

    Returns:
        LangChain ChatModel 实例（带 CallbackHandler）
    """
    return _build_model_with_middleware(config)


def _build_model_with_middleware(config: LLMConfig) -> BaseChatModel:
    """构建带中间件的 ChatModel

    1. 通过 ProviderRegistry 创建原始模型
    2. 添加 CallbackHandler 用于 Token 计数和成本追踪
    3. 返回

    Args:
        config: LLM 配置

    Returns:
        带中间件的 ChatModel 实例
    """
    registry = ProviderRegistry.get_instance()
    adapter = registry.get_adapter(config)
    model = adapter.create_model(config)

    # 添加回调处理器
    callback = LLMUsageCallbackHandler(model_name=config.model)
    model.callbacks = [callback]

    return model
