"""基础设施层 - LLM 配置管理"""

from __future__ import annotations

from typing import Optional

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    """LLM 全局配置

    从环境变量或 .env 文件加载配置。

    Attributes:
        default_provider: 默认提供商
        default_model: 默认模型
        default_temperature: 默认温度
        default_timeout: 默认超时（秒）
        default_max_retries: 默认最大重试次数
        openai_api_key: OpenAI API 密钥
        openai_api_base: OpenAI API 基础 URL
        anthropic_api_key: Anthropic API 密钥
        ollama_base_url: Ollama 基础 URL
        groq_api_key: Groq API 密钥
        deepseek_api_key: DeepSeek API 密钥
        dashscope_api_key: DashScope（通义千问）API 密钥
        zhipu_api_key: 智谱 API 密钥
    """

    # 全局默认值
    default_provider: str = Field(
        default="openai", alias="LLM_DEFAULT_PROVIDER")
    default_model: str = Field(default="gpt-4", alias="LLM_DEFAULT_MODEL")
    default_temperature: float = Field(
        default=0.7, alias="LLM_DEFAULT_TEMPERATURE")
    default_timeout: int = Field(default=60, alias="LLM_DEFAULT_TIMEOUT")
    default_max_retries: int = Field(
        default=3, alias="LLM_DEFAULT_MAX_RETRIES")
    default_max_tokens: int = Field(
        default=100000, alias="LLM_DEFAULT_MAX_TOKENS")
    default_enable_thinking: bool = Field(
        default=False, alias="LLM_ENABLE_THINKING")
    default_thinking_budget: int = Field(
        default=4000, alias="LLM_DEFAULT_THINKING_BUDGET")

    # OpenAI
    openai_api_key: Optional[SecretStr] = Field(
        default=None, alias="OPENAI_API_KEY")
    openai_api_base: Optional[str] = Field(
        default=None, alias="OPENAI_API_BASE")

    # Anthropic
    anthropic_api_key: Optional[SecretStr] = Field(
        default=None, alias="ANTHROPIC_API_KEY")

    # Ollama
    ollama_base_url: str = Field(
        default="http://localhost:11434", alias="OLLAMA_BASE_URL")

    # Groq
    groq_api_key: Optional[SecretStr] = Field(
        default=None, alias="GROQ_API_KEY")

    # DeepSeek
    deepseek_api_key: Optional[SecretStr] = Field(
        default=None, alias="DEEPSEEK_API_KEY")

    # DashScope (通义千问)
    dashscope_api_key: Optional[SecretStr] = Field(
        default=None, alias="DASHSCOPE_API_KEY")

    # Zhipu (智谱)
    zhipu_api_key: Optional[SecretStr] = Field(
        default=None, alias="ZHIPU_API_KEY")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
        extra="ignore",
    )
