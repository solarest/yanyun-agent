"""领域层 - LLM Provider 接口

定义 LLM 服务的抽象接口，遵循依赖倒置原则。
应用层依赖此接口，基础设施层提供具体实现。
"""

from abc import ABC, abstractmethod
from typing import Optional

from langchain_core.language_models import BaseChatModel


class ILLMProvider(ABC):
    """LLM 提供商接口

    职责：
    - 创建 ChatModel 实例
    - 封装 LLM 提供商的技术细节
    - 为应用层提供统一的 LLM 访问接口
    """

    @abstractmethod
    def create_chat_model(
        self,
        model: Optional[str] = None,
        temperature: float = 0.7,
        provider: Optional[str] = None,
    ) -> BaseChatModel:
        """创建 ChatModel 实例

        Args:
            model: 模型名称，为 None 时使用默认配置
            temperature: 温度参数 (0-1)
            provider: 提供商名称，为 None 时自动推断

        Returns:
            LangChain ChatModel 实例（带回调处理器）
        """
        pass
