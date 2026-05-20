"""领域层 - PromptTemplate 值对象单元测试"""

import pytest
from src.domain.entities.agent import Agent
from src.domain.entities.prompt_template import PromptTemplate
from src.domain.services.token_utils import count_tokens


class TestPromptTemplate:
    """PromptTemplate 值对象测试"""

    def test_from_agent_copies_all_fields(self) -> None:
        """测试 from_agent 工厂方法正确复制所有字段"""
        agent = Agent(
            id="a1",
            name="TestAgent",
            identity_md="# Identity\nI am a test agent",
            agents_md="# Custom Instructions\nFollow PEP 8",
            bootstrap_md="# Bootstrap\nYou are a helpful assistant",
            soul_md="# Soul\nBe concise",
            user_md="# User\nPrefers Chinese",
            memory_md="# Memory\nStore user preferences",
            tools_md="Only use read-only tools",
        )

        template = PromptTemplate.from_agent(agent)

        assert template.id == f"pt-{agent.id}"
        assert template.name == agent.name
        assert template.identity_md == agent.identity_md
        assert template.agents_md == agent.agents_md
        assert template.bootstrap_md == agent.bootstrap_md
        assert template.soul_md == agent.soul_md
        assert template.user_md == agent.user_md
        assert template.memory_md == agent.memory_md
        assert template.tools_md == agent.tools_md

    def test_empty_template(self) -> None:
        """测试空模板"""
        template = PromptTemplate(id="t1", name="Empty")
        assert template.identity_md == ""
        assert template.bootstrap_md == ""
        assert template.soul_md == ""


class TestCountTokens:
    """Token 计数函数测试"""

    def test_count_english_tokens(self) -> None:
        """测试英文 token 计数"""
        text = "Hello world" * 10  # 110 characters
        tokens = count_tokens(text)
        # 英文约 0.25 tokens/字符
        assert tokens == int(110 * 0.25)

    def test_count_chinese_tokens(self) -> None:
        """测试中文 token 计数"""
        text = "你好世界" * 10  # 40 characters
        tokens = count_tokens(text)
        # 中文约 1.5 tokens/字符
        assert tokens == int(40 * 1.5)

    def test_count_mixed_tokens(self) -> None:
        """测试混合文本 token 计数"""
        text = "Hello 你好"  # 5 English + 1 space + 2 Chinese = 8 chars
        # 6 * 0.25 + 2 * 1.5 = 1.5 + 3 = 4.5 → 4
        tokens = count_tokens(text)
        assert tokens == 4
