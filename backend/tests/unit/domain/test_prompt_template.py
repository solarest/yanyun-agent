"""领域层 - PromptTemplate 实体单元测试"""

import pytest
from src.domain.entities.agent import Agent
from src.domain.entities.prompt_template import PromptTemplate, _count_tokens


class TestPromptTemplate:
    """PromptTemplate 实体测试"""

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

    def test_get_static_prefix_order(self) -> None:
        """测试静态前缀组装顺序：BOOTSTRAP → IDENTITY → AGENTS"""
        template = PromptTemplate(
            id="t1",
            name="Test",
            identity_md="IDENTITY_CONTENT",
            agents_md="AGENTS_CONTENT",
            bootstrap_md="BOOTSTRAP_CONTENT",
        )

        prefix = template.get_static_prefix()

        assert "BOOTSTRAP_CONTENT" in prefix
        assert "IDENTITY_CONTENT" in prefix
        assert "AGENTS_CONTENT" in prefix
        # 验证顺序：BOOTSTRAP 在 IDENTITY 之前
        assert prefix.index("BOOTSTRAP_CONTENT") < prefix.index(
            "IDENTITY_CONTENT")
        assert prefix.index("IDENTITY_CONTENT") < prefix.index(
            "AGENTS_CONTENT")

    def test_get_static_suffix_order(self) -> None:
        """测试静态后缀组装顺序：SOUL → USER → MEMORY"""
        template = PromptTemplate(
            id="t2",
            name="Test",
            soul_md="SOUL_CONTENT",
            user_md="USER_CONTENT",
            memory_md="MEMORY_CONTENT",
        )

        suffix = template.get_static_suffix()

        assert "SOUL_CONTENT" in suffix
        assert "USER_CONTENT" in suffix
        assert "MEMORY_CONTENT" in suffix
        assert suffix.index("SOUL_CONTENT") < suffix.index("USER_CONTENT")
        assert suffix.index("USER_CONTENT") < suffix.index("MEMORY_CONTENT")

    def test_get_static_prefix_partial_fields(self) -> None:
        """测试部分字段为空时的前缀组装"""
        template = PromptTemplate(
            id="t3",
            name="Test",
            identity_md="# Identity\nTest agent",
        )

        prefix = template.get_static_prefix()

        assert "# Identity" in prefix
        # 空字段不应产生多余标题
        assert "AGENTS" not in prefix or prefix.count("AGENTS") == 0

    def test_get_static_suffix_partial_fields(self) -> None:
        """测试部分字段为空时的后缀组装"""
        template = PromptTemplate(
            id="t4",
            name="Test",
            soul_md="# Soul\nBe professional",
        )

        suffix = template.get_static_suffix()

        assert "# Soul" in suffix
        assert "USER" not in suffix or suffix.count("USER") == 0

    def test_estimate_static_tokens(self) -> None:
        """测试静态部分 token 预估"""
        template = PromptTemplate(
            id="t5",
            name="Test",
            identity_md="A" * 100,
            bootstrap_md="B" * 200,
            soul_md="C" * 150,
        )

        tokens = template.estimate_static_tokens()

        assert tokens > 0


class TestCountTokens:
    """Token 计数函数测试"""

    def test_count_english_tokens(self) -> None:
        """测试英文 token 计数"""
        text = "Hello world" * 10  # 110 characters
        tokens = _count_tokens(text)
        # 英文约 0.25 tokens/字符
        assert tokens == int(110 * 0.25)

    def test_count_chinese_tokens(self) -> None:
        """测试中文 token 计数"""
        text = "你好世界" * 10  # 40 characters
        tokens = _count_tokens(text)
        # 中文约 1.5 tokens/字符
        assert tokens == int(40 * 1.5)

    def test_count_mixed_tokens(self) -> None:
        """测试混合文本 token 计数"""
        text = "Hello 你好"  # 5 English + 1 space + 2 Chinese = 8 chars
        # 6 * 0.25 + 2 * 1.5 = 1.5 + 3 = 4.5 → 4
        tokens = _count_tokens(text)
        assert tokens == 4
