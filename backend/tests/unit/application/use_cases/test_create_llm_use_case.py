"""测试 - 创建 LLM 用例"""
import pytest
from unittest.mock import patch, MagicMock

from src.application.use_cases.create_llm_use_case import CreateLLMUseCase
from src.application.dtos.llm_dto import LLMConfigDTO
from src.infrastructure.llm.config import LLMSettings


def test_create_llm_use_case_execute():
    """测试执行 LLM 创建用例"""
    with patch("src.infrastructure.llm.config.LLMSettings") as mock_settings_class:
        mock_settings = MagicMock()
        mock_settings_class.return_value = mock_settings
        
        use_case = CreateLLMUseCase(mock_settings)
        
        with patch("src.application.use_cases.create_llm_use_case.create_chat_model_with_config") as mock_factory:
            mock_model = MagicMock()
            mock_factory.return_value = mock_model
            
            dto = LLMConfigDTO(
                provider="openai",
                model="gpt-4",
                temperature=0.8,
            )
            
            result = use_case.execute(dto)
            
            assert result == mock_model
            mock_factory.assert_called_once()


def test_create_llm_use_case_list_providers():
    """测试列出提供商"""
    with patch("src.infrastructure.llm.config.LLMSettings") as mock_settings_class:
        mock_settings = MagicMock()
        mock_settings_class.return_value = mock_settings
        
        use_case = CreateLLMUseCase(mock_settings)
        
        providers = use_case.list_providers()
        
        # 应该返回多个提供商
        assert len(providers) > 0
        assert any(p.name == "openai" for p in providers)
        assert any(p.name == "anthropic" for p in providers)
