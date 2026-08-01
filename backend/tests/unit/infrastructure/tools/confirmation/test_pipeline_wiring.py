"""确认管道工厂与 sub-agent/team 注入测试（非阻塞版 task 6.1 / 6.2 / 6.3）。"""

import asyncio

import pytest

from src.domain.entities.event_types import AgentEventType
from src.domain.entities.tool import (
    RegisteredTool,
    ToolContext,
    ToolPolicy,
    ToolResult,
)
from src.domain.services.sub_agent_orchestrator import SubAgentOrchestrator
from src.infrastructure.tools.confirmation.contract import CONFIRMATION_METADATA_KEY
from src.infrastructure.tools.confirmation.pipeline import build_default_pipeline
from src.infrastructure.tools.confirmation.store import (
    PendingApprovalRegistry,
    SessionApprovalStore,
    get_default_registry,
)
from src.infrastructure.tools.register.registry import ToolRegistry
from src.presentation.dependencies import get_pending_approval_registry


def _fake_shell_tool() -> RegisteredTool:
    """名为 shell 的假工具——不真正执行命令，避免测试中跑 rm -rf。"""

    async def func(input, context=None):  # noqa: ANN001
        return ToolResult(output="ran", success=True)

    return RegisteredTool(
        name="shell", description="", func=func, policy=ToolPolicy()
    )


class _RecordingEmitter:
    """记录事件但不做任何决策投递（中间件不再阻塞）。"""

    def __init__(self) -> None:
        self.events: list = []

    async def emit(self, task_id, event_type, payload):  # noqa: ANN001
        self.events.append((task_id, event_type, payload))


def _ctx(task_id, tool_call_id, emitter, session_id="sess-1") -> ToolContext:
    return ToolContext(
        task_id=task_id,
        extra={
            "tool_call_id": tool_call_id,
            "session_id": session_id,
            "event_emitter": emitter,
        },
    )


class TestBuildDefaultPipeline:
    """task 6.1：工厂产出含确认闸门的完整管道。"""

    @pytest.mark.asyncio
    async def test_dangerous_shell_returns_confirmation_required(self) -> None:
        """危险 shell → 返回 confirmation_required 元数据 + SSE 事件（非阻塞）。"""
        reg = PendingApprovalRegistry()
        store = SessionApprovalStore()
        pipeline = build_default_pipeline(registry=reg, session_store=store)

        emitter = _RecordingEmitter()
        result = await pipeline.execute(
            _fake_shell_tool(), {"command": "rm -rf build"}, _ctx("t", "c1", emitter)
        )
        # 非阻塞返回
        assert not result.success
        assert result.error == "confirmation_required"
        assert result.metadata.get(CONFIRMATION_METADATA_KEY) is True
        assert result.metadata["command"] == "rm -rf build"

        # SSE 事件已发射
        assert len(emitter.events) == 1
        assert emitter.events[0][1] == AgentEventType.TOOL_CONFIRMATION_REQUIRED

        # 已登记
        assert await reg.has("t", "c1") is True

    @pytest.mark.asyncio
    async def test_safe_command_passthrough(self) -> None:
        reg = PendingApprovalRegistry()
        store = SessionApprovalStore()
        pipeline = build_default_pipeline(registry=reg, session_store=store)
        emitter = _RecordingEmitter()
        result = await pipeline.execute(
            _fake_shell_tool(), {"command": "ls -la"}, _ctx("t", "c1", emitter)
        )
        assert result.success is True
        assert emitter.events == []


class TestSubAgentScopedRegistryGatesShell:
    """task 6.3：sub-agent 作用域注册表触发确认闸门，且共享单例跨作用域可解析。"""

    @pytest.mark.asyncio
    async def test_sub_agent_registry_gates_dangerous_shell(self) -> None:
        parent = ToolRegistry(pipeline=build_default_pipeline())
        parent.register(_fake_shell_tool())
        sub = SubAgentOrchestrator().create_sub_agent_tool_registry(
            parent,
            registry_factory=lambda: ToolRegistry(pipeline=build_default_pipeline()),
        )

        # 端点访问器与管道工厂用的是同一个共享单例（决策 θ）
        assert get_pending_approval_registry() is get_default_registry()

        shared = get_default_registry()
        emitter = _RecordingEmitter()
        result = await sub.execute(
            "shell", {"command": "rm -rf build"}, _ctx("parent-1", "c1", emitter)
        )
        assert not result.success
        assert result.error == "confirmation_required"
        assert len(emitter.events) == 1
        assert await shared.has("parent-1", "c1") is True


class TestConcurrentTeamLikeCalls:
    """task 6.2：多个 team-member 式并发危险 shell 经共享单例都能登记、互不影响。"""

    @pytest.mark.asyncio
    async def test_concurrent_dangerous_calls_all_register(self) -> None:
        shared = get_default_registry()
        n = 5

        async def one(i: int) -> bool:
            pipeline = build_default_pipeline()  # 默认 → 共享单例
            emitter = _RecordingEmitter()
            ctx = _ctx("team", f"c{i}", emitter)
            result = await pipeline.execute(
                _fake_shell_tool(), {"command": "rm -rf x"}, ctx
            )
            return (
                not result.success
                and result.error == "confirmation_required"
                and len(emitter.events) == 1
                and await shared.has("team", f"c{i}")
            )

        results = await asyncio.gather(*(one(i) for i in range(n)))
        assert all(results)
