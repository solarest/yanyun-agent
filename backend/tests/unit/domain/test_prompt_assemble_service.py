"""领域层 - PromptAssembleService 单元测试"""

import pytest
from src.domain.prompt.prompt_template import PromptTemplate
from src.domain.tool import ToolDef, ToolParameter
from src.domain.skill.skill_def import SkillDef, SkillStep
from src.domain.prompt.output_schema import OutputSchema
from src.domain.services.prompt_assemble_service import PromptAssembleService


class TestPromptAssembleService:
    """PromptAssembleService 测试"""

    def test_assemble_returns_prompt_assembly_result(self) -> None:
        """测试 assemble 返回正确的 PromptAssemblyResult"""
        template = PromptTemplate(
            id="t1",
            name="Test",
            identity_md="I am a test agent.",
            bootstrap_md="You are helpful.",
            agents_md="Follow coding standards.",
        )
        tools = [ToolDef(name="search", description="Search web")]
        skills = [SkillDef(name="review", description="Review code")]

        service = PromptAssembleService()

        result = service.assemble(
            template=template,
            tools=tools,
            skills=skills,
            workspace="/tmp/project",
            environment={"platform": "darwin", "date": "2026-04-26"},
            task="Help me debug this issue",
        )

        # 验证返回类型
        assert result.system_message is not None
        assert isinstance(result.system_message, str)
        assert result.total_token_estimate > 0
        assert result.static_prefix_tokens > 0

        # 验证 system_message 内容包含正确的层
        assert "I am a test agent." in result.system_message  # Layer 1 IDENTITY
        assert "Follow coding standards." in result.system_message  # Layer 2 AGENTS
        assert "You are helpful." in result.system_message  # Layer 3 Bootstrap
        assert "CACHE BOUNDARY" in result.system_message
        assert "# Available Tools" in result.system_message  # Layer 5
        assert "- search" in result.system_message  # Layer 5 工具名称列表
        assert "/tmp/project" in result.system_message  # Layer 6 Workspace
        assert "darwin" in result.system_message  # Layer 9 Environment
        assert "STATIC SUFFIX" in result.system_message

        # 验证 layers 元信息
        assert result.layers["tools_count"] == 1
        assert result.layers["skills_count"] == 1

    def test_assemble_tools_md_supplements_tool_usage(self) -> None:
        """测试 tools_md 注入到 Layer 4 tool_usage"""
        template = PromptTemplate(
            id="t2",
            name="Test",
            identity_md="Test agent",
            tools_md="Only use read-only file operations.",
        )
        tools = [ToolDef(name="read_file", description="Read file")]

        service = PromptAssembleService()

        result = service.assemble(template=template, tools=tools)

        # tools_md 应注入到 Layer 4 tool_usage 中
        assert "Tool Authorization Constraints" in result.system_message
        assert "Only use read-only file operations." in result.system_message

    def test_assemble_memory_conditional(self) -> None:
        """测试 Memory 条件注入（Layer 7）"""
        template = PromptTemplate(
            id="t3",
            name="Test",
            identity_md="Test agent",
            memory_md="Store user preferences in memory.",
        )

        service = PromptAssembleService()

        # memory_enabled=False
        result_off = service.assemble(template=template, memory_enabled=False)

        # memory_enabled=True
        result_on = service.assemble(template=template, memory_enabled=True)

        # memory_enabled=False 时，Layer 7 不注入 "# Memory System" 标题
        # 但 memory_md 仍会在 Layer 11 静态后缀中出现
        assert "# Memory System" not in result_off.system_message
        assert "# Memory System" in result_on.system_message
        # Layer 11 中都会出现
        assert "Store user preferences" in result_off.system_message
        assert "Store user preferences" in result_on.system_message

    def test_assemble_universal_behavior_always_on(self) -> None:
        """测试 Always-On Rules 始终注入"""
        template = PromptTemplate(
            id="t4",
            name="Test",
            identity_md="Test agent",
        )

        service = PromptAssembleService()
        result = service.assemble(template=template)

        # 3 个 Always-On Rules 应该始终存在
        assert "Communication Style" in result.system_message
        assert "Professional Objectivity" in result.system_message
        assert "Proactiveness" in result.system_message

    def test_assemble_conditional_task_management(self) -> None:
        """测试 task_management 条件注入"""
        template = PromptTemplate(
            id="t5",
            name="Test",
            identity_md="Test agent",
        )
        tools = [ToolDef(name="task_create", description="Create task")]

        service = PromptAssembleService()

        # 有 task_* 工具时
        result_with = service.assemble(template=template, tools=tools)
        assert "Task Management" in result_with.system_message

        # 无 task_* 工具时
        result_without = service.assemble(template=template, tools=[])
        assert "Task Management" not in result_without.system_message

    def test_assemble_conditional_delegation_strategy(self) -> None:
        """测试 delegation_strategy 条件注入"""
        template = PromptTemplate(
            id="t6",
            name="Test",
            identity_md="Test agent",
        )
        tools = [ToolDef(name="sessions_create", description="Create session")]

        service = PromptAssembleService()

        # 有 sessions_* 工具时
        result_with = service.assemble(template=template, tools=tools)
        assert "Delegation Strategy" in result_with.system_message

        # 无 sessions_* 工具时
        result_without = service.assemble(template=template, tools=[])
        assert "Delegation Strategy" not in result_without.system_message

    def test_assemble_skill_instructions(self) -> None:
        """测试 Skill Instructions 层生成"""
        template = PromptTemplate(
            id="t7",
            name="Test",
            identity_md="Test agent",
        )
        skills = [
            SkillDef(
                name="code_review",
                description="Review code",
                trigger_keywords=["review", "check"],
                steps=[
                    SkillStep(name="analyze", description="Analyze code"),
                    SkillStep(name="report", description="Report issues",
                              tool_name="write_file"),
                ],
            )
        ]

        service = PromptAssembleService()
        result = service.assemble(template=template, skills=skills)

        assert "<active_skills>" in result.system_message
        assert "code_review" in result.system_message
        assert "review, check" in result.system_message
        assert "</active_skills>" in result.system_message

    def test_assemble_output_schema(self) -> None:
        """测试 Output Schema 层注入"""
        template = PromptTemplate(
            id="t8",
            name="Test",
            identity_md="Test agent",
        )
        schema = OutputSchema(
            id="s1",
            name="TestSchema",
            json_schema={"type": "object", "properties": {
                "result": {"type": "string"}}},
        )

        service = PromptAssembleService()
        result = service.assemble(template=template, output_schema=schema)

        assert "Output Format" in result.system_message
        assert "JSON" in result.system_message

    def test_assemble_empty_template(self) -> None:
        """测试空模板组装"""
        template = PromptTemplate(
            id="t9",
            name="Test",
        )

        service = PromptAssembleService()
        result = service.assemble(template=template)

        # 至少包含 CACHE BOUNDARY 和 STATIC SUFFIX
        assert "CACHE BOUNDARY" in result.system_message
        assert "STATIC SUFFIX" in result.system_message
        # 但应该有 Always-On Rules
        assert "Communication Style" in result.system_message
