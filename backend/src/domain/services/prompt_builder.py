"""领域层 - PromptBuilder 领域服务"""

from src.domain.entities.agent import Agent


class PromptBuilder:
    """Prompt 构建服务

    编排领域对象，组装完整的系统提示词。
    """

    @staticmethod
    def build_system_prompt(agent: Agent) -> str:
        """构建系统提示词

        委托 Agent 实体的 build_full_system_prompt 方法组装定义域内容。

        Args:
            agent: Agent 实体

        Returns:
            组装后的完整系统提示词字符串
        """
        return agent.build_full_system_prompt()
