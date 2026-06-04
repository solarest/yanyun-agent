"""SubAgent 有界上下文 - Sub-Agent 启动器接口。"""

from abc import ABC, abstractmethod
from typing import Any


class ISubAgentLauncher(ABC):
    """Sub-Agent 启动器接口

    用于工具层调用 sub-agent 启动逻辑，而不直接依赖应用层用例。
    由应用层实现薄适配器。
    """

    @abstractmethod
    async def launch(
        self,
        agent_id: str,
        session_id: str,
        description: str,
        *,
        model: str,
        max_turns: int,
        workspace: str,
        parent_task_id: str,
        parent_system_prompt: str,
        allowed_tools: list[str] | None = None,
    ) -> Any:
        """启动一个 sub-agent 并返回执行结果"""
        ...
