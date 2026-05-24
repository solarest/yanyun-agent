"""ExecutionPipeline + 中间件单元测试"""

import asyncio

import pytest

from src.domain.tool import (
    RegisteredTool,
    ToolContext,
    ToolParameter,
    ToolPolicy,
    ToolResult,
)
from src.infrastructure.tools.pipeline import ExecutionPipeline
from src.infrastructure.tools.middleware.timeout import TimeoutMiddleware
from src.infrastructure.tools.middleware.rate_limit import RateLimitMiddleware
from src.infrastructure.tools.middleware.security import SecurityMiddleware
from src.infrastructure.tools.middleware.sandbox import SandboxMiddleware


def _make_tool(
    name: str = "echo",
    policy: ToolPolicy | None = None,
    category: str = "general",
) -> RegisteredTool:
    """创建测试用工具"""
    async def func(input: dict, context: ToolContext | None = None) -> ToolResult:
        return ToolResult(output=input.get("msg", "ok"))

    return RegisteredTool(
        name=name,
        description="Test tool",
        func=func,
        category=category,
        policy=policy or ToolPolicy(),
    )


class TestExecutionPipeline:
    @pytest.mark.asyncio
    async def test_direct_execution_no_middleware(self) -> None:
        pipeline = ExecutionPipeline()
        t = _make_tool()
        result = await pipeline.execute(t, {"msg": "hello"})
        assert result.output == "hello"
        assert result.success is True
        assert "duration_ms" in result.metadata

    @pytest.mark.asyncio
    async def test_middleware_order_onion(self) -> None:
        order: list[str] = []

        class MW1:
            async def process(self, tool, input, context, next_handler):
                order.append("MW1_before")
                result = await next_handler(tool, input, context)
                order.append("MW1_after")
                return result

        class MW2:
            async def process(self, tool, input, context, next_handler):
                order.append("MW2_before")
                result = await next_handler(tool, input, context)
                order.append("MW2_after")
                return result

        pipeline = ExecutionPipeline(middlewares=[MW1(), MW2()])
        t = _make_tool()
        await pipeline.execute(t, {"msg": "hi"})
        assert order == ["MW1_before", "MW2_before", "MW2_after", "MW1_after"]

    @pytest.mark.asyncio
    async def test_catches_exception(self) -> None:
        async def bad_func(input: dict, context=None) -> ToolResult:
            raise ValueError("boom")

        t = RegisteredTool(name="bad", description="", func=bad_func)
        pipeline = ExecutionPipeline()
        result = await pipeline.execute(t, {})
        assert result.success is False
        assert "boom" in result.error or ""
        assert "duration_ms" in result.metadata


class TestTimeoutMiddleware:
    @pytest.mark.asyncio
    async def test_stops_slow_tool(self) -> None:
        async def slow_func(input: dict, context=None) -> ToolResult:
            await asyncio.sleep(10)
            return ToolResult(output="done")

        t = RegisteredTool(
            name="slow", description="",
            func=slow_func,
            policy=ToolPolicy(timeout_ms=100),
        )
        pipeline = ExecutionPipeline(middlewares=[TimeoutMiddleware()])
        result = await pipeline.execute(t, {})
        assert result.success is False
        assert result.error == "timeout"

    @pytest.mark.asyncio
    async def test_allows_fast_tool(self) -> None:
        t = _make_tool(policy=ToolPolicy(timeout_ms=5000))
        pipeline = ExecutionPipeline(middlewares=[TimeoutMiddleware()])
        result = await pipeline.execute(t, {"msg": "fast"})
        assert result.success is True
        assert result.output == "fast"


class TestRateLimitMiddleware:
    @pytest.mark.asyncio
    async def test_blocks_excess_calls(self) -> None:
        t = _make_tool(policy=ToolPolicy(max_calls_per_minute=2))
        mw = RateLimitMiddleware()
        pipeline = ExecutionPipeline(middlewares=[mw])

        r1 = await pipeline.execute(t, {"msg": "1"})
        r2 = await pipeline.execute(t, {"msg": "2"})
        r3 = await pipeline.execute(t, {"msg": "3"})

        assert r1.success is True
        assert r2.success is True
        assert r3.success is False
        assert r3.error == "rate_limited"


class TestSecurityMiddleware:
    @pytest.mark.asyncio
    async def test_blocks_unlisted_tool(self) -> None:
        t = _make_tool(name="forbidden")
        mw = SecurityMiddleware(allowed_tools=["allowed_tool"])
        pipeline = ExecutionPipeline(middlewares=[mw])
        result = await pipeline.execute(t, {})
        assert result.success is False
        assert result.error == "permission_denied"

    @pytest.mark.asyncio
    async def test_allows_listed_tool(self) -> None:
        t = _make_tool(name="allowed_tool")
        mw = SecurityMiddleware(allowed_tools=["allowed_tool"])
        pipeline = ExecutionPipeline(middlewares=[mw])
        result = await pipeline.execute(t, {"msg": "ok"})
        assert result.success is True

    @pytest.mark.asyncio
    async def test_no_whitelist_allows_all(self) -> None:
        t = _make_tool(name="any_tool")
        mw = SecurityMiddleware(allowed_tools=None)
        pipeline = ExecutionPipeline(middlewares=[mw])
        result = await pipeline.execute(t, {"msg": "ok"})
        assert result.success is True

    @pytest.mark.asyncio
    async def test_blocks_forbidden_path(self) -> None:
        t = _make_tool(
            name="file_read",
            category="file",
            policy=ToolPolicy(allowed_paths=("/workspace",)),
        )
        mw = SecurityMiddleware()
        pipeline = ExecutionPipeline(middlewares=[mw])
        result = await pipeline.execute(t, {"path": "/etc/passwd"})
        assert result.success is False
        assert result.error == "path_not_allowed"

    @pytest.mark.asyncio
    async def test_blocks_path_outside_workspace_by_default(self, tmp_path) -> None:
        t = _make_tool(name="file_read", category="file")
        mw = SecurityMiddleware()
        pipeline = ExecutionPipeline(middlewares=[mw])
        result = await pipeline.execute(
            t,
            {"path": "../outside.txt"},
            ToolContext(task_id="t1", workspace=str(tmp_path / "workspace")),
        )
        assert result.success is False
        assert result.error == "path_not_allowed"


class TestSandboxMiddleware:
    @pytest.mark.asyncio
    async def test_non_sandboxed_passes_through(self) -> None:
        t = _make_tool(policy=ToolPolicy(sandboxed=False))
        pipeline = ExecutionPipeline(middlewares=[SandboxMiddleware()])
        result = await pipeline.execute(t, {"msg": "ok"})
        assert result.success is True
        assert "sandboxed" not in result.metadata

    @pytest.mark.asyncio
    async def test_sandboxed_marks_metadata(self) -> None:
        t = _make_tool(policy=ToolPolicy(sandboxed=True))
        pipeline = ExecutionPipeline(middlewares=[SandboxMiddleware()])
        result = await pipeline.execute(t, {"msg": "ok"})
        assert result.success is True
        assert result.metadata.get("sandboxed") is True
