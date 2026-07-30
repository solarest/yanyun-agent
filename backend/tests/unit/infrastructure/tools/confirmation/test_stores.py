"""审批存储测试（非阻塞版 task 3.1 / 3.2）。

PendingApprovalRegistry 仅追踪存在性（不再持有 Future）。
"""

import pytest

from src.infrastructure.tools.confirmation.store import (
    PendingApprovalRegistry,
    SessionApprovalStore,
)


class TestPendingApprovalRegistry:
    @pytest.mark.asyncio
    async def test_register_then_has_returns_true(self) -> None:
        reg = PendingApprovalRegistry()
        await reg.register("task-1", "call-1")
        assert await reg.has("task-1", "call-1") is True

    @pytest.mark.asyncio
    async def test_has_unknown_returns_false(self) -> None:
        reg = PendingApprovalRegistry()
        assert await reg.has("task-1", "nope") is False

    @pytest.mark.asyncio
    async def test_remove_clears_registration(self) -> None:
        reg = PendingApprovalRegistry()
        await reg.register("task-1", "call-1")
        await reg.remove("task-1", "call-1")
        assert await reg.has("task-1", "call-1") is False

    @pytest.mark.asyncio
    async def test_remove_nonexistent_no_error(self) -> None:
        reg = PendingApprovalRegistry()
        await reg.remove("task-1", "nope")  # 不应抛异常

    @pytest.mark.asyncio
    async def test_register_twice_overwrites(self) -> None:
        reg = PendingApprovalRegistry()
        await reg.register("task-1", "call-1")
        await reg.register("task-1", "call-1")  # 覆盖，不抛异常
        assert await reg.has("task-1", "call-1") is True

    @pytest.mark.asyncio
    async def test_different_keys_independent(self) -> None:
        reg = PendingApprovalRegistry()
        await reg.register("task-1", "call-1")
        await reg.register("task-1", "call-2")
        assert await reg.has("task-1", "call-1") is True
        assert await reg.has("task-1", "call-2") is True
        await reg.remove("task-1", "call-1")
        assert await reg.has("task-1", "call-1") is False
        assert await reg.has("task-1", "call-2") is True


class TestSessionApprovalStore:
    @pytest.mark.asyncio
    async def test_allow_then_is_allowed(self) -> None:
        s = SessionApprovalStore()
        assert await s.is_allowed("sess-1", "sudo") is False
        await s.allow("sess-1", "sudo")
        assert await s.is_allowed("sess-1", "sudo") is True

    @pytest.mark.asyncio
    async def test_different_session_isolated(self) -> None:
        s = SessionApprovalStore()
        await s.allow("sess-1", "sudo")
        assert await s.is_allowed("sess-2", "sudo") is False

    @pytest.mark.asyncio
    async def test_different_category_isolated(self) -> None:
        s = SessionApprovalStore()
        await s.allow("sess-1", "sudo")
        assert await s.is_allowed("sess-1", "rm-recursive") is False
