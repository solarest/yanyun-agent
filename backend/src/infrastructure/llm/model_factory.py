"""基础设施层 - LangChain ChatModel 工厂（统一版本）"""

from typing import Optional

from langchain_core.language_models import BaseChatModel

from src.domain.value_objects.llm_config import LLMConfig, LLMProvider
from src.infrastructure.llm.providers.registry import ProviderRegistry
from src.infrastructure.llm.callback import LLMCallLogger, LLMUsageCallbackHandler


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
    settings = LLMSettings()
    if model is None:
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
        max_tokens=settings.default_max_tokens,
        enable_thinking=settings.default_enable_thinking,
        thinking_budget=settings.default_thinking_budget,
    )

    return _build_model_with_middleware(config)


def _build_model_with_middleware(config: LLMConfig) -> BaseChatModel:
    """构建带中间件的 ChatModel

    1. 通过 ProviderRegistry 创建原始模型
    2. 挂载 CallbackHandler：
       - LLMUsageCallbackHandler: Token 计数与成本追踪
       - LLMCallLogger: 在真正调用 LLM 前/后记录完整入参与出参（含 tools）
    3. 返回

    Args:
        config: LLM 配置

    Returns:
        带中间件的 ChatModel 实例
    """
    registry = ProviderRegistry.get_instance()
    adapter = registry.get_adapter(config)
    model = adapter.create_model(config)

    # 挂载回调处理器
    usage_callback = LLMUsageCallbackHandler(model_name=config.model)
    call_logger = LLMCallLogger()
    model.callbacks = [usage_callback, call_logger]

    return model
