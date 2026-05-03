"""领域层 - ToolDef 和 ConversationMessage 实体单元测试"""

import pytest
from src.domain.entities.tool_def import ToolDef, ToolParameter
from src.domain.entities.skill_def import SkillDef, SkillStep
from src.domain.entities.output_schema import OutputSchema
from src.domain.entities.conversation import ConversationMessage, MessageGroup, ToolCall


class TestToolDef:
    """ToolDef 实体测试"""

    def test_tool_def_to_prompt_section(self) -> None:
        """测试工具定义生成为 XML 格式"""
        tool = ToolDef(
            name="web_search",
            description="Search the web for information",
            parameters=[
                ToolParameter(name="query", type="string",
                              description="Search query", required=True),
                ToolParameter(name="limit", type="number",
                              description="Max results", required=False),
            ],
            returns="Search results as JSON"
        )

        result = tool.to_prompt_section()

        assert '<tool name="web_search">' in result
        assert '<description>Search the web for information</description>' in result
        assert '<param name="query" type="string" required="true">Search query</param>' in result
        assert '<param name="limit" type="number" required="false">Max results</param>' in result
        assert "<returns>Search results as JSON</returns>" in result
        assert "</tool>" in result

    def test_tool_def_with_enum(self) -> None:
        """测试带枚举值的参数"""
        tool = ToolDef(
            name="set_config",
            description="Set configuration",
            parameters=[
                ToolParameter(
                    name="mode",
                    type="string",
                    description="Configuration mode",
                    required=True,
                    enum=["dev", "prod", "test"],
                ),
            ],
        )

        result = tool.to_prompt_section()

        assert '<enum>dev, prod, test</enum>' in result

    def test_tool_def_no_parameters(self) -> None:
        """测试无参数的工具"""
        tool = ToolDef(
            name="get_time",
            description="Get current time",
        )

        result = tool.to_prompt_section()

        assert '<tool name="get_time">' in result
        assert "<parameters>" not in result
        assert "</tool>" in result


class TestSkillDef:
    """SkillDef 实体测试"""

    def test_skill_def_to_prompt_section(self) -> None:
        """测试技能定义生成为 Prompt 段落"""
        skill = SkillDef(
            name="code_review",
            description="Systematic code review",
            trigger_keywords=["review", "check code"],
            steps=[
                SkillStep(name="analyze",
                          description="Analyze code structure"),
                SkillStep(name="check_security",
                          description="Check security", tool_name="web_search"),
            ],
        )

        result = skill.to_prompt_section()

        assert "### code_review" in result
        assert "Systematic code review" in result
        assert "**Triggers:** review, check code" in result
        assert "**Steps:**" in result
        assert "1. **analyze**: Analyze code structure" in result
        assert "2. **check_security** (using `web_search`): Check security" in result


class TestOutputSchema:
    """OutputSchema 实体测试"""

    def test_output_schema_to_json(self) -> None:
        """测试 Schema 序列化为 JSON"""
        schema = OutputSchema(
            id="s1",
            name="TestSchema",
            json_schema={
                "type": "object",
                "properties": {
                    "result": {"type": "string"},
                    "count": {"type": "integer"},
                },
            },
        )

        json_str = schema.to_json_string()

        assert '"type": "object"' in json_str
        assert '"result"' in json_str
        assert '"count"' in json_str

    def test_output_schema_validate(self) -> None:
        """测试 Schema 验证"""
        valid_schema = OutputSchema(
            id="s2",
            name="Valid",
            json_schema={"type": "object"},
        )
        assert valid_schema.validate_schema() is True

        invalid_schema = OutputSchema(
            id="s3",
            name="Invalid",
            json_schema={"invalid": "data"},
        )
        assert invalid_schema.validate_schema() is False


class TestConversationMessage:
    """ConversationMessage 实体测试"""

    def test_to_api_message_user_role(self) -> None:
        """测试 user 角色消息转换"""
        msg = ConversationMessage(role="user", content="Hello")

        api_msg = msg.to_api_message()

        assert api_msg == {"role": "user", "content": "Hello"}

    def test_to_api_message_assistant_with_tool_calls(self) -> None:
        """测试 assistant 角色带工具调用的消息转换"""
        msg = ConversationMessage(
            role="assistant",
            content="",
            tool_calls=[
                ToolCall(id="tc_001", name="read_file",
                         arguments={"path": "main.py"})
            ]
        )

        api_msg = msg.to_api_message()

        assert api_msg["role"] == "assistant"
        assert len(api_msg["tool_calls"]) == 1
        assert api_msg["tool_calls"][0]["id"] == "tc_001"
        assert api_msg["tool_calls"][0]["type"] == "function"
        assert api_msg["tool_calls"][0]["function"]["name"] == "read_file"

    def test_to_api_message_tool_role(self) -> None:
        """测试 tool 角色消息转换"""
        msg = ConversationMessage(
            role="tool",
            content="file content here",
            tool_call_id="tc_001"
        )

        api_msg = msg.to_api_message()

        assert api_msg == {
            "role": "tool",
            "tool_call_id": "tc_001",
            "content": "file content here"
        }

    def test_to_api_message_system_role(self) -> None:
        """测试 system 角色消息转换"""
        msg = ConversationMessage(
            role="system", content="You are an assistant")

        api_msg = msg.to_api_message()

        assert api_msg == {"role": "system", "content": "You are an assistant"}

    def test_estimate_tokens_with_tool_calls(self) -> None:
        """测试带工具调用的消息 token 预估"""
        msg = ConversationMessage(
            role="assistant",
            content="Let me check",
            tool_calls=[
                ToolCall(id="tc_001", name="search",
                         arguments={"query": "test"})
            ]
        )

        tokens = msg.estimate_tokens()

        assert tokens > 0


class TestMessageGroup:
    """MessageGroup 实体测试"""

    def test_message_group_dialogue(self) -> None:
        """测试 dialogue 类型消息组"""
        group = MessageGroup(
            type="dialogue",
            messages=[
                ConversationMessage(role="user", content="Hello"),
                ConversationMessage(role="assistant", content="Hi there"),
            ]
        )

        token_count = group.compute_token_count()

        assert token_count > 0
        assert group.token_count == token_count

    def test_message_group_tool_call_round(self) -> None:
        """测试 tool_call_round 类型消息组"""
        group = MessageGroup(
            type="tool_call_round",
            messages=[
                ConversationMessage(
                    role="assistant", content="",
                    tool_calls=[
                        ToolCall(id="tc_001", name="read_file", arguments={"path": "a.py"})]
                ),
                ConversationMessage(
                    role="tool", content="file content", tool_call_id="tc_001"),
            ]
        )

        token_count = group.compute_token_count()

        assert token_count > 0
        assert len(group.messages) == 2
