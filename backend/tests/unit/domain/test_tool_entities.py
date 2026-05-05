"""领域层实体单元测试 - ToolDef / ToolResult / ToolPolicy / RegisteredTool"""

import pytest

from src.domain.entities.tool import (
    RegisteredTool,
    ToolContext,
    ToolDef,
    ToolParameter,
    ToolPolicy,
    ToolResult,
)


class TestToolParameter:
    def test_required_parameter(self) -> None:
        p = ToolParameter(name="query", type="string",
                          description="Search query")
        assert p.required is True
        assert p.enum is None

    def test_optional_parameter_with_enum(self) -> None:
        p = ToolParameter(
            name="depth",
            type="string",
            description="Search depth",
            required=False,
            enum=["basic", "advanced"],
        )
        assert p.required is False
        assert p.enum == ["basic", "advanced"]


class TestToolDef:
    def test_to_llm_schema_basic(self) -> None:
        """测试生成基本 LLM Schema"""
        td = ToolDef(
            name="web_search",
            description="Search the web",
            parameters=[
                ToolParameter(name="query", type="string",
                              description="Search query"),
            ],
            returns="Search results",
            category="web_search",
        )
        schema = td.to_llm_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "web_search"
        assert schema["function"]["description"] == "Search the web"
        assert "query" in schema["function"]["parameters"]["properties"]

    def test_to_llm_schema_with_enum(self) -> None:
        """测试带枚举的 LLM Schema"""
        td = ToolDef(
            name="test",
            description="Test tool",
            parameters=[
                ToolParameter(
                    name="mode",
                    type="string",
                    description="Mode",
                    enum=["fast", "slow"],
                ),
            ],
        )
        schema = td.to_llm_schema()
        mode_prop = schema["function"]["parameters"]["properties"]["mode"]
        assert mode_prop["enum"] == ["fast", "slow"]

    def test_to_llm_schema_no_params(self) -> None:
        """测试无参数的 LLM Schema"""
        td = ToolDef(name="simple", description="Simple tool")
        schema = td.to_llm_schema()
        assert schema["function"]["parameters"]["properties"] == {}

    def test_to_llm_schema_optional_param(self) -> None:
        """测试可选参数的 LLM Schema"""
        td = ToolDef(
            name="t",
            description="d",
            parameters=[
                ToolParameter(name="x", type="integer",
                              description="val", required=False),
            ],
        )
        schema = td.to_llm_schema()
        params = schema["function"]["parameters"]
        assert "x" in params["properties"]
        assert "x" not in params.get("required", [])


class TestToolResult:
    def test_default_success(self) -> None:
        r = ToolResult(output="hello")
        assert r.success is True
        assert r.error is None
        assert r.metadata == {}

    def test_error_case(self) -> None:
        r = ToolResult(output="fail", success=False, error="timeout")
        assert r.success is False
        assert r.error == "timeout"

    def test_metadata_mutable(self) -> None:
        r = ToolResult(output="ok")
        r.metadata["duration_ms"] = 100
        assert r.metadata["duration_ms"] == 100


class TestToolContext:
    def test_minimal_context(self) -> None:
        ctx = ToolContext(task_id="t1")
        assert ctx.task_id == "t1"
        assert ctx.workspace == ""
        assert ctx.user_id is None

    def test_full_context(self) -> None:
        ctx = ToolContext(
            task_id="t1",
            workspace="/tmp",
            user_id="u1",
            agent_id="a1",
            extra={"key": "val"},
        )
        assert ctx.workspace == "/tmp"
        assert ctx.extra["key"] == "val"


class TestToolPolicy:
    def test_defaults(self) -> None:
        p = ToolPolicy()
        assert p.timeout_ms == 30000
        assert p.max_calls_per_minute == 60
        assert p.sandboxed is False

    def test_frozen(self) -> None:
        p = ToolPolicy()
        with pytest.raises(AttributeError):
            p.timeout_ms = 5000  # type: ignore[misc]

    def test_custom_values(self) -> None:
        p = ToolPolicy(
            timeout_ms=5000,
            max_calls_per_minute=10,
            sandboxed=True,
            allowed_paths=("/workspace",),
        )
        assert p.timeout_ms == 5000
        assert p.allowed_paths == ("/workspace",)


class TestRegisteredTool:
    def test_to_tool_def(self) -> None:
        async def dummy(input: dict, context: None = None) -> ToolResult:
            return ToolResult(output="ok")

        rt = RegisteredTool(
            name="web_search",
            description="Search the web",
            func=dummy,
            parameters=[
                ToolParameter(name="query", type="string",
                              description="q", required=True),
            ],
            returns="Search results",
            category="web_search",
        )

        td = rt.to_tool_def()
        assert td.name == "web_search"
        assert td.description == "Search the web"
        assert len(td.parameters) == 1
        assert td.category == "web_search"
        assert td.returns == "Search results"

    def test_to_tool_def_prompt_section(self) -> None:
        async def dummy(input: dict, context: None = None) -> ToolResult:
            return ToolResult(output="ok")

        rt = RegisteredTool(
            name="test_tool",
            description="A test",
            func=dummy,
            parameters=[
                ToolParameter(name="x", type="string", description="input"),
            ],
        )
        result = rt.to_tool_def().to_prompt_section()
        # 现在只返回工具名称
        assert result == "- test_tool"
