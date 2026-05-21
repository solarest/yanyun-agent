"""测试 - LLM 配置"""
import pytest
from unittest.mock import patch

from src.infrastructure.llm.config import LLMSettings


def test_llm_settings_default_values():
    """测试 LLM 配置的默认值"""
    with patch.dict("os.environ", {}, clear=True):
        # 创建不加载 .env 文件的配置实例
        settings = LLMSettings(_env_file=None)

        assert settings.default_provider == "openai"
        assert settings.default_model == "gpt-4"
        assert settings.default_temperature == 0.7
        assert settings.default_timeout == 60
        assert settings.default_max_retries == 3
        assert settings.default_max_tokens == 8192


def test_llm_settings_from_env():
    """测试从环境变量加载配置"""
    import os
    with patch.dict("os.environ", {
        "LLM_DEFAULT_PROVIDER": "anthropic",
        "LLM_DEFAULT_MODEL": "claude-3-sonnet",
        "LLM_DEFAULT_TEMPERATURE": "0.9",
        "LLM_DEFAULT_MAX_TOKENS": "4096",
    }, clear=True):
        settings = LLMSettings()

        assert settings.default_provider == "anthropic"
        assert settings.default_model == "claude-3-sonnet"
        assert settings.default_temperature == 0.9
        assert settings.default_max_tokens == 4096
