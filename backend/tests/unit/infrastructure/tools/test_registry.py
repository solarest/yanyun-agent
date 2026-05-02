"""ToolRegistry 单元测试"""

import pytest

from src.domain.entities.tool import (
    RegisteredTool,
    ToolContext,
    ToolPolicy,
    ToolResult,
)
from src.infrastructure.tools.decorator import clear_collected_tools, tool
from src.infrastructure.tools.pipeline import ExecutionPipeline
from src.infrastructure.tools.registry import ToolRegistry


@pytest.fixture(autouse=True)
def _clean_collector():
    clear_collected_tools()
    yield
    clear_collected_tools()


def _make_tool(name: str = "echo") -> RegisteredTool:
    async def func(input: dict, context: ToolContext | None = None) -> ToolResult:
        return ToolResult(output=input.get("msg", "default"))

    return RegisteredTool(name=name, description=f"Tool {name}", func=func)


class TestToolRegistry:
    def test_register_and_resolve(self) -> None:
        registry = ToolRegistry()
        t = _make_tool("test")
        registry.register(t)
        assert registry.resolve("test") is t
        assert registry.tool_count == 1

    def test_unregister(self) -> None:
        registry = ToolRegistry()
        t = _make_tool("test")
        registry.register(t)
        assert registry.unregister("test") is True
        assert registry.resolve("test") is None
        assert registry.tool_count == 0

    def test_unregister_nonexistent(self) -> None:
        registry = ToolRegistry()
        assert registry.unregister("nope") is False

    def test_list_tools_all(self) -> None:
        registry = ToolRegistry()
        registry.register(_make_tool("a"))
        registry.register(_make_tool("b"))
        tools = registry.list_tools()
        assert len(tools) == 2

    def test_list_tools_by_category(self) -> None:
        registry = ToolRegistry()
        t1 = _make_tool("a")
        t1.category = "file"
        t2 = _make_tool("b")
        t2.category = "web"
        registry.register(t1)
        registry.register(t2)

        file_tools = registry.list_tools(category="file")
        assert len(file_tools) == 1
        assert file_tools[0].name == "a"

    def test_get_tool_defs(self) -> None:
        registry = ToolRegistry()
        registry.register(_make_tool("test"))
        defs = registry.get_tool_defs()
        assert len(defs) == 1
        assert defs[0].name == "test"

    @pytest.mark.asyncio
    async def test_execute_success(self) -> None:
        registry = ToolRegistry()
        registry.register(_make_tool("echo"))
        result = await registry.execute("echo", {"msg": "hello"})
        assert result.success is True
        assert result.output == "hello"

    @pytest.mark.asyncio
    async def test_execute_tool_not_found(self) -> None:
        registry = ToolRegistry()
        result = await registry.execute("nonexistent", {})
        assert result.success is False
        assert "not found" in result.output.lower()

    @pytest.mark.asyncio
    async def test_execute_through_pipeline(self) -> None:
        called = []

        class TrackingMW:
            async def process(self, tool, input, context, next_handler):
                called.append(tool.name)
                return await next_handler(tool, input, context)

        pipeline = ExecutionPipeline(middlewares=[TrackingMW()])
        registry = ToolRegistry(pipeline=pipeline)
        registry.register(_make_tool("tracked"))
        await registry.execute("tracked", {"msg": "test"})
        assert called == ["tracked"]

    def test_auto_register_collected(self) -> None:
        @tool(name="auto_tool", description="Auto registered")
        async def auto_tool(x: str) -> ToolResult:
            """Args:
                x: val
            """
            return ToolResult(output=x)

        registry = ToolRegistry()
        registry.auto_register_collected()
        assert registry.resolve("auto_tool") is not None
