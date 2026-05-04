"""task_create 和 task_update 工具单元测试"""

import pytest

from src.domain.entities.tool import ToolContext, ToolResult
from src.infrastructure.tools.builtin.task_create import task_create
from src.infrastructure.tools.builtin.task_update import task_update
from src.infrastructure.tools.decorator import clear_collected_tools


@pytest.fixture(autouse=True)
def _clean():
    clear_collected_tools()
    yield
    clear_collected_tools()


# === task_create 测试 ===


class TestTaskCreate:
    @pytest.mark.asyncio
    async def test_empty_goal(self) -> None:
        rt = task_create._registered_tool  # type: ignore[attr-defined]
        result = await rt.func({"goal": "   ", "tasks": [{"id": 1, "description": "test"}]}, None)
        assert result.success is False
        assert result.error == "invalid_input"
        assert "goal cannot be empty" in result.output

    @pytest.mark.asyncio
    async def test_empty_tasks(self) -> None:
        rt = task_create._registered_tool  # type: ignore[attr-defined]
        result = await rt.func({"goal": "Test goal", "tasks": []}, None)
        assert result.success is False
        assert result.error == "invalid_input"
        assert "tasks cannot be empty" in result.output

    @pytest.mark.asyncio
    async def test_empty_task_description(self) -> None:
        rt = task_create._registered_tool  # type: ignore[attr-defined]
        result = await rt.func(
            {"goal": "Test goal", "tasks": [
                {"id": 1, "description": "   "}]}, None
        )
        assert result.success is False
        assert result.error == "invalid_input"
        assert "description cannot be empty" in result.output

    @pytest.mark.asyncio
    async def test_duplicate_task_ids(self) -> None:
        rt = task_create._registered_tool  # type: ignore[attr-defined]
        result = await rt.func(
            {
                "goal": "Test goal",
                "tasks": [
                    {"id": 1, "description": "Task 1"},
                    {"id": 1, "description": "Task 2"},
                ],
            },
            None,
        )
        assert result.success is False
        assert result.error == "invalid_input"
        assert "duplicate task id" in result.output

    @pytest.mark.asyncio
    async def test_invalid_dependency(self) -> None:
        rt = task_create._registered_tool  # type: ignore[attr-defined]
        result = await rt.func(
            {
                "goal": "Test goal",
                "tasks": [
                    {"id": 1, "description": "Task 1", "depends_on": [99]},
                ],
            },
            None,
        )
        assert result.success is False
        assert result.error == "invalid_input"
        assert "depends on non-existent task" in result.output

    @pytest.mark.asyncio
    async def test_valid_task_creation(self) -> None:
        rt = task_create._registered_tool  # type: ignore[attr-defined]
        result = await rt.func(
            {
                "goal": "Test goal",
                "tasks": [
                    {"id": 1, "description": "Task 1", "depends_on": []},
                    {"id": 2, "description": "Task 2", "depends_on": [1]},
                    {"id": 3, "description": "Task 3", "depends_on": []},
                ],
            },
            None,
        )
        assert result.success is True
        assert "Task List: Test goal" in result.output
        assert "Task 1: Task 1" in result.output
        assert "Task 2: Task 2 (depends on: 1)" in result.output
        assert "Task 3: Task 3" in result.output
        assert result.metadata["type"] == "task_create"
        assert result.metadata["goal"] == "Test goal"
        assert result.metadata["task_count"] == 3

    @pytest.mark.asyncio
    async def test_auto_assign_ids(self) -> None:
        rt = task_create._registered_tool  # type: ignore[attr-defined]
        result = await rt.func(
            {
                "goal": "Test goal",
                "tasks": [
                    {"description": "Task 1"},
                    {"description": "Task 2"},
                ],
            },
            None,
        )
        assert result.success is True
        tasks = result.metadata["tasks"]
        assert tasks[0]["id"] == 1
        assert tasks[1]["id"] == 2


# === task_update 测试 ===


class TestTaskUpdate:
    @pytest.mark.asyncio
    async def test_invalid_status(self) -> None:
        rt = task_update._registered_tool  # type: ignore[attr-defined]
        context = ToolContext(task_id="test-task")
        result = await rt.func(
            {"task_id": 1, "status": "invalid", "result": "Done"}, context
        )
        assert result.success is False
        assert result.error == "invalid_input"
        assert "status must be" in result.output

    @pytest.mark.asyncio
    async def test_empty_result(self) -> None:
        rt = task_update._registered_tool  # type: ignore[attr-defined]
        context = ToolContext(task_id="test-task")
        result = await rt.func(
            {"task_id": 1, "status": "completed", "result": "   "}, context
        )
        assert result.success is False
        assert result.error == "invalid_input"
        assert "result cannot be empty" in result.output

    @pytest.mark.asyncio
    async def test_missing_context(self) -> None:
        rt = task_update._registered_tool  # type: ignore[attr-defined]
        result = await rt.func(
            {"task_id": 1, "status": "completed", "result": "Done"}, None
        )
        assert result.success is False
        assert result.error == "invalid_context"

    @pytest.mark.asyncio
    async def test_valid_update_completed(self) -> None:
        rt = task_update._registered_tool  # type: ignore[attr-defined]
        context = ToolContext(task_id="test-task")
        result = await rt.func(
            {"task_id": 1, "status": "completed",
                "result": "Task done successfully"},
            context,
        )
        assert result.success is True
        assert "Task 1 marked as completed" in result.output
        assert result.metadata["type"] == "task_update"
        assert result.metadata["task_id"] == 1
        assert result.metadata["status"] == "completed"
        assert result.metadata["result"] == "Task done successfully"

    @pytest.mark.asyncio
    async def test_valid_update_failed(self) -> None:
        rt = task_update._registered_tool  # type: ignore[attr-defined]
        context = ToolContext(task_id="test-task")
        result = await rt.func(
            {"task_id": 2, "status": "failed", "result": "Error occurred"}, context
        )
        assert result.success is True
        assert "Task 2 marked as failed" in result.output
        assert result.metadata["status"] == "failed"
