"""测试 - LLM 工厂"""
import pytest
from unittest.mock import patch, MagicMock

from src.infrastructure.llm.model_factory import create_chat_model
from src.domain.entities.llm import LLMConfig, LLMProvider


def test_create_chat_model_with_openai():
    """测试创建 OpenAI 模型"""
    with patch("src.infrastructure.llm.providers.registry.ProviderRegistry.get_instance") as mock_registry:
        # 配置 mock
        mock_adapter = MagicMock()
        mock_model = MagicMock()
        mock_adapter.create_model.return_value = mock_model
        mock_registry.return_value.get_adapter.return_value = mock_adapter
        
        model = create_chat_model(model="gpt-4", temperature=0.7)
        
        assert model == mock_model
        config = mock_adapter.create_model.call_args.args[0]
        assert config.max_tokens == 8192


def test_create_chat_model_with_anthropic():
    """测试创建 Anthropic 模型"""
    with patch("src.infrastructure.llm.providers.registry.ProviderRegistry.get_instance") as mock_registry:
        mock_adapter = MagicMock()
        mock_model = MagicMock()
        mock_adapter.create_model.return_value = mock_model
        mock_registry.return_value.get_adapter.return_value = mock_adapter
        
        model = create_chat_model(model="claude-3-sonnet", provider="anthropic")
        
        assert model == mock_model


def test_create_chat_model_uses_max_tokens_from_env(monkeypatch):
    """测试默认最大输出 token 可通过环境变量配置"""
    monkeypatch.setenv("LLM_DEFAULT_MAX_TOKENS", "4096")
    with patch("src.infrastructure.llm.providers.registry.ProviderRegistry.get_instance") as mock_registry:
        mock_adapter = MagicMock()
        mock_model = MagicMock()
        mock_adapter.create_model.return_value = mock_model
        mock_registry.return_value.get_adapter.return_value = mock_adapter

        model = create_chat_model(model="qwen3-max", provider="qwen")

        assert model == mock_model
        config = mock_adapter.create_model.call_args.args[0]
        assert config.max_tokens == 4096
