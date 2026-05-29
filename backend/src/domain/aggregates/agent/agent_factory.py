"""Agent 工厂 — 封装 Agent 聚合根的复杂创建逻辑。"""

from src.domain.aggregates.agent.agent import Agent

DEFAULT_IDENTITY = "You are a helpful AI assistant."


class AgentFactory:
    """Agent 工厂

    封装 Agent 创建逻辑，确保创建的 Agent 拥有完整且一致的初始状态。
    """

    @staticmethod
    def create_default(name: str, description: str = "", model: str = "gpt-4") -> Agent:
        """创建具有默认配置的 Agent"""
        return Agent(
            name=name,
            description=description,
            identity_md=DEFAULT_IDENTITY,
        )

    @staticmethod
    def create_from_template(name: str, template: Agent) -> Agent:
        """从模板 Agent 复制创建新 Agent"""
        return Agent(
            name=name,
            description=template.description,
            vibes=template.vibes,
            identity_md=template.identity_md,
            soul_md=template.soul_md,
            agents_md=template.agents_md,
            bootstrap_md=template.bootstrap_md,
            memory_md=template.memory_md,
            tools_md=template.tools_md,
            user_md=template.user_md,
        )
