"""领域层 - LLM 错误处理器接口

定义 LLM 调用异常的处理策略，采用工厂/职责链模式。
每个 handler 自行判断是否能处理该错误，返回状态更新 dict 或 re-raise。
"""

from abc import ABC, abstractmethod
from typing import Any


class ILLMErrorHandler(ABC):
    """LLM 错误处理器抽象基类"""

    @abstractmethod
    def can_handle(self, error: BaseException) -> bool:
        """判断是否能处理该错误"""
        ...

    @abstractmethod
    def handle(self, error: BaseException, state: dict, context: Any) -> dict:
        """处理错误并返回状态更新 dict

        Args:
            error: 异常对象
            state: 当前 AgentState
            context: NodeContext 实例

        Returns:
            状态更新字典

        Raises:
            error: 如果不匹配（由 DefaultErrorHandler 实现）
        """
        ...


class LLMErrorHandlerRegistry:
    """LLM 错误处理器注册表（职责链模式）

    按注册顺序遍历 handlers，第一个 can_handle 返回 True 的 handler 处理错误。
    如果所有 handler 都不匹配，re-raise error（交给 BaseNode._handle_error）。
    """

    def __init__(self, handlers: list[ILLMErrorHandler] | None = None):
        self._handlers: list[ILLMErrorHandler] = list(handlers or [])

    def register(self, handler: ILLMErrorHandler) -> None:
        """注册一个错误处理器"""
        self._handlers.append(handler)

    def handle(self, error: BaseException, state: dict, context: Any) -> dict:
        """遍历 handlers 找到匹配的处理，都不匹配则 re-raise

        Args:
            error: 异常对象
            state: 当前 AgentState
            context: NodeContext 实例

        Returns:
            状态更新字典

        Raises:
            error: 所有 handler 都不匹配时 re-raise
        """
        for handler in self._handlers:
            if handler.can_handle(error):
                return handler.handle(error, state, context)
        raise error
