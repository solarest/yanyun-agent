"""基础设施层 - LangChain ChatModel 工厂（统一版本）"""

from typing import Optional

from langchain_core.language_models import BaseChatModel

from src.domain.entities.llm import LLMConfig, LLMProvider
from src.infrastructure.llm.providers.registry import ProviderRegistry
from src.infrastructure.llm.callback import LLMUsageCallbackHandler


def _infer_provider(model: str) -> str:
    """根据模型名称推断提供商"""
    model_lower = model.lower()
    if "claude" in model_lower:
        return "anthropic"
    if model_lower.startswith("qwen"):
        return "qwen"
    if model_lower.startswith("deepseek"):
        return "deepseek"
    if model_lower.startswith("glm"):
        return "zhipu"
    if model_lower.startswith("llama") or model_lower.startswith("mixtral"):
        return "groq"
    return "openai"


def create_chat_model(
    model: Optional[str] = None,
    temperature: float = 0.7,
    provider: Optional[str] = None,
) -> BaseChatModel:
    """创建 ChatModel 实例（保持向后兼容）

    Args:
        model: 模型名称，为 None 时使用 LLMSettings 默认值
        temperature: 温度参数
        provider: 提供商名称，如果为 None 则根据模型名推断

    Returns:
        LangChain ChatModel 实例（带 CallbackHandler）
    """
    from src.infrastructure.llm.config import LLMSettings

    # 使用 LLMSettings 默认值
    if model is None:
        settings = LLMSettings()
        model = settings.default_model
        if provider is None:
            provider = settings.default_provider

    # 自动推断提供商
    if provider is None:
        provider = _infer_provider(model)

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
