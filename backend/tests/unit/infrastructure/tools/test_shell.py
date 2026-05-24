"""Shell 工具单元测试"""

import pytest

from src.domain.tool import ToolContext, ToolResult
from src.infrastructure.tools.builtin.shell import shell
from src.infrastructure.tools.decorator import clear_collected_tools


@pytest.fixture(autouse=True)
def _clean():
    clear_collected_tools()
    yield
    clear_collected_tools()


class TestShellTool:
    """Shell 工具测试类"""

    @pytest.mark.asyncio
    async def test_shell_simple_command(self):
        """测试简单命令执行"""
        rt = shell._registered_tool  # type: ignore[attr-defined]
        result = await rt.func({"command": "echo 'hello world'"}, None)
        assert result.success is True
        assert "hello world" in result.output
        assert result.metadata["returncode"] == 0

    @pytest.mark.asyncio
    async def test_shell_empty_command(self):
        """测试空命令"""
        rt = shell._registered_tool  # type: ignore[attr-defined]
        result = await rt.func({"command": "   "}, None)
        assert result.success is False
        assert result.error == "invalid_input"
        assert "cannot be empty" in result.output

    @pytest.mark.asyncio
    async def test_shell_working_dir(self):
        """测试工作目录设置"""
        import os

        # 使用已知目录
        rt = shell._registered_tool  # type: ignore[attr-defined]
        result = await rt.func({"command": "pwd", "working_dir": "/tmp"}, None)
        assert result.success is True
        assert "/tmp" in result.output
        assert result.metadata["cwd"] == "/tmp"

    @pytest.mark.asyncio
    async def test_shell_invalid_directory(self):
        """测试无效工作目录"""
        rt = shell._registered_tool  # type: ignore[attr-defined]
        result = await rt.func({"command": "ls", "working_dir": "/nonexistent/path"}, None)
        assert result.success is False
        assert result.error == "invalid_directory"

    @pytest.mark.asyncio
    async def test_shell_command_with_context(self):
        """测试带上下文的命令执行"""
        context = ToolContext(task_id="test-task", workspace="/tmp")
        rt = shell._registered_tool  # type: ignore[attr-defined]
        result = await rt.func({"command": "pwd"}, context)
        assert result.success is True
        assert result.metadata["cwd"] == "/tmp"

    @pytest.mark.asyncio
    async def test_shell_stderr_output(self):
        """测试标准错误输出"""
        rt = shell._registered_tool  # type: ignore[attr-defined]
        result = await rt.func({"command": "ls /nonexistent_directory_12345"}, None)
        # 命令失败，返回非零退出码
        assert result.success is False
        assert "Standard Error" in result.output or "No such file" in result.output
        assert result.metadata["returncode"] != 0

    @pytest.mark.asyncio
    async def test_shell_timeout(self):
        """测试超时控制"""
        # sleep 10 秒，但设置超时为 1 秒
        rt = shell._registered_tool  # type: ignore[attr-defined]
        result = await rt.func({"command": "sleep 10", "timeout_ms": 1000}, None)
        assert result.success is False
        assert result.error == "timeout"
        assert "timed out" in result.output

    @pytest.mark.asyncio
    async def test_shell_output_truncation(self):
        """测试输出截断"""
        # 生成超过 10000 字符的输出
        rt = shell._registered_tool  # type: ignore[attr-defined]
        result = await rt.func({"command": "python3 -c \"print('x' * 15000)\""}, None)
        assert result.success is True
        assert "truncated" in result.output
        assert result.metadata["stdout_truncated"] is True

    @pytest.mark.asyncio
    async def test_shell_multiple_commands(self):
        """测试多条命令（使用 &&）"""
        rt = shell._registered_tool  # type: ignore[attr-defined]
        result = await rt.func({"command": "echo 'first' && echo 'second'"}, None)
        assert result.success is True
        assert "first" in result.output
        assert "second" in result.output

    @pytest.mark.asyncio
    async def test_shell_environment_variable(self):
        """测试环境变量"""
        rt = shell._registered_tool  # type: ignore[attr-defined]
        result = await rt.func({"command": "echo $HOME"}, None)
        assert result.success is True
        assert result.metadata["returncode"] == 0

    @pytest.mark.asyncio
    async def test_shell_metadata(self):
        """测试元数据完整性"""
        rt = shell._registered_tool  # type: ignore[attr-defined]
        result = await rt.func({"command": "echo test", "working_dir": "/tmp"}, None)
        assert "command" in result.metadata
        assert "cwd" in result.metadata
        assert "returncode" in result.metadata
        assert "stdout_length" in result.metadata
        assert "stderr_length" in result.metadata
        assert result.metadata["command"] == "echo test"
        assert result.metadata["cwd"] == "/tmp"
