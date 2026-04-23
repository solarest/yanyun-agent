"""应用层 - PromptBuilder 服务"""

from src.domain.entities.agent import Agent


class PromptBuilder:
    """Prompt 构建服务

    编排领域对象和运行时上下文，渲染系统提示词。
    """

    @staticmethod
    def build_system_prompt(agent: Agent, workspace: str) -> str:
        """构建系统提示词

        将 Agent 的属性和运行时上下文代入模板，渲染为最终的系统提示词。

        Args:
            agent: Agent 实体
            workspace: 工作目录路径

        Returns:
            渲染后的系统提示词字符串
        """
        context = {
            "name": agent.name,
            "role": agent.role,
            "workspace": workspace,
        }
        return agent.render_system_prompt(context)
