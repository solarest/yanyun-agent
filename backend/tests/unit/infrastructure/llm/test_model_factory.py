"""测试 - LLM 工厂"""
import pytest
from unittest.mock import patch, MagicMock

from src.infrastructure.llm.model_factory import create_chat_model
from src.domain.llm.llm import LLMConfig, LLMProvider


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


def test_create_chat_model_with_anthropic():
    """测试创建 Anthropic 模型"""
    with patch("src.infrastructure.llm.providers.registry.ProviderRegistry.get_instance") as mock_registry:
        mock_adapter = MagicMock()
        mock_model = MagicMock()
        mock_adapter.create_model.return_value = mock_model
        mock_registry.return_value.get_adapter.return_value = mock_adapter
        
        model = create_chat_model(model="claude-3-sonnet", provider="anthropic")
        
        assert model == mock_model
