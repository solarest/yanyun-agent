"""领域层 - LLM 配置实体"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class LLMProvider(str, Enum):
    """LLM 提供商枚举"""
    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"
    GROQ = "groq"
    DEEPSEEK = "deepseek"
    QWEN = "qwen"
    ZHIPU = "zhipu"


@dataclass
class LLMConfig:
    """LLM 配置实体
    
    描述一个 LLM 实例的完整配置，是纯数据类。
    
    Attributes:
        provider: LLM 提供商
        model: 模型名称
        temperature: 温度参数 (0-2)
        max_tokens: 最大生成 token 数
        timeout: 超时时间（秒）
        max_retries: 最大重试次数
        api_base: API 基础 URL
        api_key: API 密钥
        extra: 提供商特有参数
    """
    provider: LLMProvider
    model: str
    temperature: float = 0.7
    max_tokens: int | None = None
    timeout: int = 60
    max_retries: int = 3
    api_base: str | None = None
    api_key: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
