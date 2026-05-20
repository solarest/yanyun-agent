"""单元测试 - session_spawn 工具

测试 session_spawn 工具的核心逻辑。
由于 @tool 装饰器将函数包装为接受 (input: dict, context: ToolContext) 签名，
我们直接测试内部实现函数。
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from src.domain.entities.tool import ToolContext, ToolResult
from src.domain.entities.task import Task, TaskStatus


@pytest.fixture
def mock_use_case():
    """创建模拟的 SendMessageUseCase"""
    use_case = AsyncMock()
    use_case.execute = AsyncMock(return_value={
        "task_id": "sub-456",
        "user_message": MagicMock(),
    })
    return use_case


@pytest.fixture
def mock_task_repo():
    """创建模拟的 TaskRepository"""
    repo = AsyncMock()

    # 模拟 task 创建
    async def mock_add(task):
        return task
    repo.add = AsyncMock(side_effect=mock_add)

    # 模拟 task 查询（第一次返回未完成，第二次返回完成）
    call_count = {"count": 0}

    async def mock_get_by_id(task_id):
        call_count["count"] += 1
        if call_count["count"] <= 2:
            # 尚未完成
            task = Task(
                id=task_id,
                message="Test",
                workspace="/tmp",
                status=TaskStatus.RUNNING,
            )
            task.completed_at = None
            return task
        else:
            # 已完成
            task = Task(
                id=task_id,
                message="Test",
                workspace="/tmp",
                status=TaskStatus.COMPLETED,
            )
            task.completed_at = MagicMock()
            task.result = "Task completed successfully"
            task.error = None
            return task

    repo.get_by_id = AsyncMock(side_effect=mock_get_by_id)
    return repo


@pytest.fixture
def mock_event_emitter():
    """创建模拟的 EventEmitter"""
    emitter = AsyncMock()
    emitter.emit = AsyncMock()
    return emitter


@pytest.fixture
def valid_context(mock_use_case, mock_task_repo, mock_event_emitter):
    """创建有效的 context"""
    return ToolContext(
        task_id="task-123",
        workspace="/tmp/workspace",
        user_id="user-1",
        agent_id="agent-1",
        extra={
            "send_message_use_case": mock_use_case,
            "task_repo": mock_task_repo,
            "event_emitter": mock_event_emitter,
            "parent_state": {"system_prompt": "Test prompt", "model": "gpt-4"},
            "parent_agent_id": "agent-1",
            "parent_session_id": "session-1",
            "parent_task_id": "task-123",
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

    def test_tool_definition_guides_parallel_atomic_subtasks(self):
        """工具定义应明确引导模型拆分为多个并行原子 sub-agent。"""
        from src.infrastructure.tools.builtin import session_spawn as session_spawn_module

        rt = session_spawn_module.session_spawn._registered_tool
        assert "一个原子" in rt.description
        assert "不要把多个日期、多个文件、多个主题或多个查询合并" in rt.description
        assert "近 10 天天气应创建 10 个 sub-agent" in rt.description

        description_param = next(p for p in rt.parameters if p.name == "description")
        assert "单个原子子任务" in description_param.description
        assert "不要写成" in description_param.description

    @pytest.mark.asyncio
    async def test_sync_mode_success(self, valid_context, mock_use_case, mock_event_emitter):
        """测试同步模式成功"""
        result = await call_session_spawn(
            description="Process data",
            context=valid_context,
        )

        assert result.success is True
        assert "Sub-agent completed" in result.output
        assert "Task completed successfully" in result.output
        assert result.metadata["status"] == "completed"

        # 验证 use_case.execute 被调用
        mock_use_case.execute.assert_called_once()
        call_kwargs = mock_use_case.execute.call_args.kwargs
        assert call_kwargs["is_sub_agent"] is True
        assert call_kwargs["sub_agent_description"] == "Process data"

        # 验证事件发射
        assert mock_event_emitter.emit.call_count >= 2  # started + completed

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
    async def test_missing_use_case_fails(self, mock_task_repo, mock_event_emitter):
        """测试缺少 use_case 失败"""
        from src.infrastructure.tools.builtin import session_spawn as session_spawn_module
        original_func = session_spawn_module.session_spawn._registered_tool.func

        context = ToolContext(
            task_id="task-123",
            workspace="/tmp",
            extra={
                "task_repo": mock_task_repo,
                "event_emitter": mock_event_emitter,
                "parent_state": {},
                "parent_agent_id": "agent-1",
                "parent_session_id": "session-1",
            },
        )

        result = await original_func({"description": "Test"}, context)

        assert result.success is False
        assert "send_message_use_case not available" in result.output

    @pytest.mark.asyncio
    async def test_missing_task_repo_fails(self, mock_use_case, mock_event_emitter):
        """测试缺少 task_repo 失败"""
        from src.infrastructure.tools.builtin import session_spawn as session_spawn_module
        original_func = session_spawn_module.session_spawn._registered_tool.func

        context = ToolContext(
            task_id="task-123",
            workspace="/tmp",
            extra={
                "send_message_use_case": mock_use_case,
                "event_emitter": mock_event_emitter,
                "parent_state": {},
                "parent_agent_id": "agent-1",
                "parent_session_id": "session-1",
            },
        )

        result = await original_func({"description": "Test"}, context)

        assert result.success is False
        assert "task_repo not available" in result.output

    @pytest.mark.asyncio
    async def test_use_case_exception_handling(self, valid_context, mock_use_case):
        """测试 use_case 异常处理"""
        mock_use_case.execute.side_effect = Exception("Test error")

        result = await call_session_spawn(
            description="Test",
            context=valid_context,
        )

        assert result.success is False
        assert "Test error" in result.output

    @pytest.mark.asyncio
    async def test_with_custom_tools_list(self, valid_context, mock_use_case):
        """测试自定义工具列表"""
        result = await call_session_spawn(
            description="Test",
            tools=["file_read", "file_write"],
            context=valid_context,
        )

        assert result.success is True
        call_kwargs = mock_use_case.execute.call_args.kwargs
        assert call_kwargs["allowed_tools"] == ["file_read", "file_write"]
