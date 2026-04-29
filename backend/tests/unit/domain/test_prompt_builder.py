"""领域层 - PromptBuilder 单元测试"""

from src.domain.entities.agent import Agent
from src.domain.services.prompt_builder import PromptBuilder


class TestPromptBuilder:
    """PromptBuilder 测试"""

    def test_delegates_to_entity(self) -> None:
        agent = Agent(
            bootstrap_md="System init",
            identity_md="I am agent",
        )
        result = PromptBuilder.build_system_prompt(agent)
        expected = agent.build_full_system_prompt()
        assert result == expected

    def test_empty_agent(self) -> None:
        agent = Agent()
        result = PromptBuilder.build_system_prompt(agent)
        assert result == ""
