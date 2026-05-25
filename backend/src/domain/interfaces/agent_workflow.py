"""领域层 - Agent 工作流构建器接口。"""

from abc import ABC, abstractmethod
from typing import Any


class IAgentWorkflowBuilder(ABC):
    """Agent 工作流构建器接口

    定义 LangGraph StateGraph 的构建契约。应用层通过此接口启动 agent loop，
    不依赖具体的工作流编译实现。
    """

    @abstractmethod
    def build(self) -> Any:
        """构建并返回编译后的 StateGraph"""
        ...
