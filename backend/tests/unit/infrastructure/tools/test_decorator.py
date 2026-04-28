"""@tool 装饰器单元测试"""

import pytest

from src.domain.entities.tool import ToolResult
from src.infrastructure.tools.decorator import (
    _extract_parameters,
    _parse_docstring_params,
    _python_type_to_schema_type,
    clear_collected_tools,
    get_collected_tools,
    tool,
)


@pytest.fixture(autouse=True)
def _clean_collector():
    """每个测试前清空全局收集器"""
    clear_collected_tools()
    yield
    clear_collected_tools()


class TestExtractParameters:
    def test_from_typed_function(self) -> None:
        async def sample(query: str, count: int = 5, verbose: bool = False) -> ToolResult:
            """Sample tool

            Args:
                query: Search query
                count: Result count
                verbose: Enable verbose output
            """
            return ToolResult(output="ok")

        params = _extract_parameters(sample)
        assert len(params) == 3
        assert params[0].name == "query"
        assert params[0].type == "string"
        assert params[0].required is True
        assert params[1].name == "count"
        assert params[1].type == "integer"
        assert params[1].required is False
        assert params[2].name == "verbose"
        assert params[2].type == "boolean"
        assert params[2].description == "Enable verbose output"

    def test_skips_context_param(self) -> None:
        async def sample(query: str, context: None = None) -> ToolResult:
            """Args:
                query: Search query
            """
            return ToolResult(output="ok")

        params = _extract_parameters(sample)
        assert len(params) == 1
        assert params[0].name == "query"

    def test_skips_self_and_ctx(self) -> None:
        async def sample(self: None, query: str, ctx: None = None) -> ToolResult:
            """Args:
                query: val
            """
            return ToolResult(output="ok")

        params = _extract_parameters(sample)
        assert len(params) == 1
        assert params[0].name == "query"


class TestParseDocstringParams:
    def test_google_style(self) -> None:
        doc = """A tool

        Args:
            query: Search query
            count: Number of results
        """
        result = _parse_docstring_params(doc)
        assert result["query"] == "Search query"
        assert result["count"] == "Number of results"

    def test_empty_docstring(self) -> None:
        result = _parse_docstring_params("")
        assert result == {}

    def test_stops_at_returns(self) -> None:
        doc = """Tool

        Args:
            x: input value

        Returns:
            output value
        """
        result = _parse_docstring_params(doc)
        assert "x" in result
        assert len(result) == 1


class TestPythonTypeToSchemaType:
    def test_basic_types(self) -> None:
        assert _python_type_to_schema_type(str) == "string"
        assert _python_type_to_schema_type(int) == "integer"
        assert _python_type_to_schema_type(float) == "number"
        assert _python_type_to_schema_type(bool) == "boolean"
        assert _python_type_to_schema_type(list) == "array"
        assert _python_type_to_schema_type(dict) == "object"

    def test_unknown_type_defaults_to_string(self) -> None:
        assert _python_type_to_schema_type(bytes) == "string"


class TestToolDecorator:
    def test_auto_collects(self) -> None:
        @tool(name="test_tool", description="A test tool")
        async def test_tool(x: str) -> ToolResult:
            """Args:
                x: Input value
            """
            return ToolResult(output=x)

        collected = get_collected_tools()
        assert len(collected) == 1
        assert collected[0].name == "test_tool"
        assert collected[0].description == "A test tool"

    def test_preserves_name(self) -> None:
        @tool(name="custom_name", description="desc")
        async def my_func(x: str) -> ToolResult:
            """Args:
                x: val
            """
            return ToolResult(output=x)

        assert get_collected_tools()[0].name == "custom_name"

    def test_default_name_from_func(self) -> None:
        @tool(description="desc")
        async def my_tool(x: str) -> ToolResult:
            """Args:
                x: val
            """
            return ToolResult(output=x)

        assert get_collected_tools()[0].name == "my_tool"

    def test_policy_values(self) -> None:
        @tool(
            name="t", description="d",
            timeout_ms=5000, max_calls_per_minute=10,
            requires_approval=True, risk_level="high",
        )
        async def t(x: str) -> ToolResult:
            """Args:
                x: val
            """
            return ToolResult(output=x)

        rt = get_collected_tools()[0]
        assert rt.policy.timeout_ms == 5000
        assert rt.policy.max_calls_per_minute == 10
        assert rt.policy.requires_approval is True
        assert rt.policy.risk_level == "high"

    @pytest.mark.asyncio
    async def test_wrapped_function_returns_tool_result(self) -> None:
        @tool(name="echo", description="Echo tool")
        async def echo(msg: str) -> ToolResult:
            """Args:
                msg: Message
            """
            return ToolResult(output=msg)

        rt = get_collected_tools()[0]
        result = await rt.func({"msg": "hello"}, None)
        assert result.output == "hello"
        assert result.success is True

    @pytest.mark.asyncio
    async def test_wrapped_str_return_normalized(self) -> None:
        @tool(name="str_tool", description="d")
        async def str_tool(x: str) -> str:
            """Args:
                x: val
            """
            return f"result: {x}"

        rt = get_collected_tools()[0]
        result = await rt.func({"x": "hello"}, None)
        assert isinstance(result, ToolResult)
        assert result.output == "result: hello"

    @pytest.mark.asyncio
    async def test_sync_function_wrapped(self) -> None:
        @tool(name="sync_tool", description="d")
        def sync_tool(x: str) -> str:
            """Args:
                x: val
            """
            return f"sync: {x}"

        rt = get_collected_tools()[0]
        result = await rt.func({"x": "test"}, None)
        assert isinstance(result, ToolResult)
        assert result.output == "sync: test"
