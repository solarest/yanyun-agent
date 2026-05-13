"""单元测试 - session_spawn 工具

测试 session_spawn 工具的核心逻辑。
由于 @tool 装饰器将函数包装为接受 (input: dict, context: ToolContext) 签名，
我们直接测试内部实现函数。
"""

import pytest
from unittest.mock import AsyncMock
from src.domain.entities.tool import ToolContext, ToolResult


@pytest.fixture
def mock_launcher():
    """创建模拟的 launcher"""
    launcher = AsyncMock()
    launcher.launch_sync = AsyncMock(return_value={
        "status": "completed",
        "sub_task_id": "sub-456",
        "result": "Task completed successfully",
    })
    return launcher


@pytest.fixture
def valid_context(mock_launcher):
    """创建有效的 context"""
    return ToolContext(
        task_id="task-123",
        workspace="/tmp/workspace",
        user_id="user-1",
        agent_id="agent-1",
        extra={
            "sub_agent_launcher": mock_launcher,
            "parent_state": {"system_prompt": "Test prompt", "user_message": "Test"},
            "parent_agent_id": "agent-1",
            "parent_session_id": "session-1",
            "parent_task_id": "task-123",
            "user_message": "Test user message",
        },
    )


async def call_session_spawn(description: str, context: ToolContext, tools: list = None) -> ToolResult:
    """调用 session_spawn 内部实现函数"""
    # 直接导入并调用内部函数逻辑（绕过装饰器）
    # 模拟装饰器包装后的调用方式
    input_dict = {
        "description": description,
    }
    if tools is not None:
        input_dict["tools"] = tools

    # 获取原始函数（绕过装饰器）
    from src.infrastructure.tools.builtin import session_spawn as session_spawn_module
    # 装饰器在函数上附加了 _registered_tool
    original_func = session_spawn_module.session_spawn._registered_tool.func

    # 调用包装后的函数（接受 input dict 和 context）
    return await original_func(input_dict, context)


class TestSessionSpawn:
    """session_spawn 工具测试"""

    @pytest.mark.asyncio
    async def test_sync_mode_success(self, valid_context, mock_launcher):
        """测试同步模式成功"""
        result = await call_session_spawn(
            description="Process data",
            context=valid_context,
        )

        assert result.success is True
        assert "Sub-agent completed" in result.output
        assert "Task completed successfully" in result.output
        assert result.metadata["status"] == "completed"

        mock_launcher.launch_sync.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_description_fails(self, valid_context):
        """测试空描述失败"""
        result = await call_session_spawn(
            description="",
            context=valid_context,
        )

        assert result.success is False
        assert "description cannot be empty" in result.output

    @pytest.mark.asyncio
    async def test_whitespace_description_fails(self, valid_context):
        """测试空白描述失败"""
        result = await call_session_spawn(
            description="   ",
            context=valid_context,
        )

        assert result.success is False

    @pytest.mark.asyncio
    async def test_missing_context_fails(self):
        """测试缺少 context 失败"""
        from src.infrastructure.tools.builtin import session_spawn as session_spawn_module
        original_func = session_spawn_module.session_spawn._registered_tool.func

        result = await original_func({"description": "Test"}, None)

        assert result.success is False
        assert "context is required" in result.output

    @pytest.mark.asyncio
    async def test_missing_launcher_fails(self):
        """测试缺少 launcher 失败"""
        from src.infrastructure.tools.builtin import session_spawn as session_spawn_module
        original_func = session_spawn_module.session_spawn._registered_tool.func

        context = ToolContext(
            task_id="task-123",
            workspace="/tmp",
            extra={
                "parent_state": {},
                "parent_agent_id": "agent-1",
                "parent_session_id": "session-1",
            },
        )

        result = await original_func({"description": "Test"}, context)

        assert result.success is False
        assert "sub_agent_launcher not available" in result.output

    @pytest.mark.asyncio
    async def test_missing_parent_state_fails(self, mock_launcher):
        """测试缺少 parent_state 失败"""
        from src.infrastructure.tools.builtin import session_spawn as session_spawn_module
        original_func = session_spawn_module.session_spawn._registered_tool.func

        context = ToolContext(
            task_id="task-123",
            workspace="/tmp",
            extra={
                "sub_agent_launcher": mock_launcher,
                "parent_agent_id": "agent-1",
                "parent_session_id": "session-1",
            },
        )

        result = await original_func({"description": "Test"}, context)

        assert result.success is False
        assert "parent_state not available" in result.output

    @pytest.mark.asyncio
    async def test_launcher_exception_handling(self, valid_context, mock_launcher):
        """测试 launcher 异常处理"""
        mock_launcher.launch_sync.side_effect = Exception("Test error")

        result = await call_session_spawn(
            description="Test",
            context=valid_context,
        )

        assert result.success is False
        assert "Test error" in result.output

    @pytest.mark.asyncio
    async def test_with_custom_tools_list(self, valid_context, mock_launcher):
        """测试自定义工具列表"""
        result = await call_session_spawn(
            description="Test",
            tools=["file_read", "file_write"],
            context=valid_context,
        )

        assert result.success is True
        call_args = mock_launcher.launch_sync.call_args
        assert call_args.kwargs["allowed_tools"] == ["file_read", "file_write"]
