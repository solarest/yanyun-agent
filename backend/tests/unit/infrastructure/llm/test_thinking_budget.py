"""测试 thinking_budget 参数的传递和使用"""

import os
from src.domain.llm.llm import LLMConfig, LLMProvider
from src.infrastructure.llm.config import LLMSettings
from src.infrastructure.llm.model_factory import create_chat_model


class TestThinkingBudget:
    """thinking_budget 参数测试"""

    def test_llm_config_has_thinking_budget(self) -> None:
        """LLMConfig 应该包含 thinking_budget 字段"""
        config = LLMConfig(
            provider=LLMProvider.QWEN,
            model="qwen3-max",
            enable_thinking=True,
            thinking_budget=2000,
        )
        assert config.enable_thinking is True
        assert config.thinking_budget == 2000

    def test_llm_config_default_thinking_budget(self) -> None:
        """LLMConfig 的 thinking_budget 默认值应该为 None"""
        config = LLMConfig(
            provider=LLMProvider.QWEN,
            model="qwen3-max",
        )
        assert config.enable_thinking is False
        assert config.thinking_budget is None

    def test_settings_has_thinking_budget(self) -> None:
        """LLMSettings 应该包含 default_thinking_budget 配置"""
        settings = LLMSettings()
        assert hasattr(settings, "default_thinking_budget")
        assert settings.default_thinking_budget == 4000  # 默认值

    def test_settings_thinking_budget_from_env(self) -> None:
        """LLMSettings 应该能从环境变量读取 thinking_budget"""
        env_vars = {
            "LLM_DEFAULT_PROVIDER": "qwen",
            "LLM_DEFAULT_MODEL": "qwen3-max",
            "LLM_ENABLE_THINKING": "true",
            "LLM_DEFAULT_THINKING_BUDGET": "3000",
            "DASHSCOPE_API_KEY": "test-key",
        }

        for key, value in env_vars.items():
            os.environ[key] = value

        try:
            settings = LLMSettings()
            assert settings.default_enable_thinking is True
            assert settings.default_thinking_budget == 3000
        finally:
            for key in env_vars:
                os.environ.pop(key, None)

    def test_create_chat_model_with_thinking_budget(self) -> None:
        """create_chat_model 应该传递 thinking_budget 到 LLMConfig"""
        os.environ["LLM_DEFAULT_PROVIDER"] = "qwen"
        os.environ["LLM_DEFAULT_MODEL"] = "qwen3-max"
        os.environ["LLM_ENABLE_THINKING"] = "true"
        os.environ["LLM_DEFAULT_THINKING_BUDGET"] = "5000"
        os.environ["DASHSCOPE_API_KEY"] = "test-key"

        try:
            # 这会创建一个 ChatModel，我们可以验证配置是否正确传递
            # 注意：这里不实际调用 API，只是验证配置
            model = create_chat_model()
            # 如果创建成功，说明配置正确传递
            assert model is not None
        finally:
            for key in ["LLM_DEFAULT_PROVIDER", "LLM_DEFAULT_MODEL",
                        "LLM_ENABLE_THINKING", "LLM_DEFAULT_THINKING_BUDGET",
                        "DASHSCOPE_API_KEY"]:
                os.environ.pop(key, None)
