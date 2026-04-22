"""应用层 - 创建 LLM 用例"""
from langchain_core.language_models import BaseChatModel

from src.application.dtos.llm_dto import LLMConfigDTO, LLMProviderInfoDTO
from src.domain.entities.llm import LLMConfig, LLMProvider
from src.infrastructure.llm.config import LLMSettings
from src.infrastructure.llm.model_factory import create_chat_model_with_config


class CreateLLMUseCase:
    """创建 LLM 实例用例
    
    封装 LLM 实例创建流程，供表现层使用。
    
    Attributes:
        settings: LLM 全局配置
    """
    
    def __init__(self, settings: LLMSettings):
        self.settings = settings
    
    def execute(self, dto: LLMConfigDTO) -> BaseChatModel:
        """创建 LLM 实例
        
        Args:
            dto: LLM 配置 DTO
            
        Returns:
            LangChain ChatModel 实例
        """
        config = LLMConfig(
            provider=LLMProvider(dto.provider),
            model=dto.model,
            temperature=dto.temperature,
            max_tokens=dto.max_tokens,
            timeout=dto.timeout,
            max_retries=dto.max_retries,
            extra=dto.extra,
        )
        
        return create_chat_model_with_config(config)
    
    def list_providers(self) -> list[LLMProviderInfoDTO]:
        """列出可用提供商
        
        Returns:
            提供商信息列表
        """
        providers = []
        for provider in LLMProvider:
            providers.append(LLMProviderInfoDTO(
                name=provider.value,
                available_models=self._get_models_for_provider(provider),
            ))
        return providers
    
    def _get_models_for_provider(self, provider: LLMProvider) -> list[str]:
        """获取提供商的可用模型列表"""
        models = {
            LLMProvider.OPENAI: ["gpt-4", "gpt-4-turbo", "gpt-3.5-turbo", "gpt-4o", "gpt-4o-mini"],
            LLMProvider.ANTHROPIC: ["claude-3-opus", "claude-3-sonnet", "claude-3-haiku", "claude-3-5-sonnet"],
            LLMProvider.OLLAMA: ["llama3", "mistral", "phi3"],
            LLMProvider.GROQ: ["llama3-70b-8192", "llama3-8b-8192"],
            LLMProvider.DEEPSEEK: ["deepseek-chat"],
            LLMProvider.QWEN: ["qwen-turbo", "qwen-plus"],
            LLMProvider.ZHIPU: ["glm-4", "glm-3-turbo"],
        }
        return models.get(provider, [])
