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
        p = ToolParameter(name="query", type="string", description="Search query")
        assert p.required is True
        assert p.enum is None

    def test_optional_parameter_with_enum(self) -> None:
        p = ToolParameter(
            name="depth", type="string", description="Search depth",
            required=False, enum=["basic", "advanced"],
        )
        assert p.required is False
        assert p.enum == ["basic", "advanced"]


class TestToolDef:
    def test_to_prompt_section_generates_xml(self) -> None:
        td = ToolDef(
            name="web_search",
            description="Search the web",
            parameters=[
                ToolParameter(name="query", type="string", description="Search query"),
            ],
            returns="Search results",
            category="web_search",
        )
        xml = td.to_prompt_section()
        assert '<tool name="web_search">' in xml
        assert "<description>Search the web</description>" in xml
        assert '<param name="query"' in xml
        assert 'type="string"' in xml
        assert 'required="true"' in xml
        assert "<returns>Search results</returns>" in xml
        assert "</tool>" in xml

    def test_to_prompt_section_with_enum(self) -> None:
        td = ToolDef(
            name="test",
            description="Test tool",
            parameters=[
                ToolParameter(
                    name="mode", type="string", description="Mode",
                    enum=["fast", "slow"],
                ),
            ],
        )
        xml = td.to_prompt_section()
        assert "<enum>fast, slow</enum>" in xml

    def test_to_prompt_section_no_params(self) -> None:
        td = ToolDef(name="simple", description="Simple tool")
        xml = td.to_prompt_section()
        assert "<parameters>" not in xml
        assert "<returns>" not in xml

    def test_to_prompt_section_optional_param(self) -> None:
        td = ToolDef(
            name="t",
            description="d",
            parameters=[
                ToolParameter(name="x", type="integer", description="val", required=False),
            ],
        )
        xml = td.to_prompt_section()
        assert 'required="false"' in xml


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
            task_id="t1", workspace="/tmp", user_id="u1",
            agent_id="a1", extra={"key": "val"},
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
            timeout_ms=5000, max_calls_per_minute=10,
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
                ToolParameter(name="query", type="string", description="q", required=True),
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
            name="test_tool", description="A test", func=dummy,
            parameters=[
                ToolParameter(name="x", type="string", description="input"),
            ],
        )
        xml = rt.to_tool_def().to_prompt_section()
        assert '<tool name="test_tool">' in xml
