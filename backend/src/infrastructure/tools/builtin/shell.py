"""基础设施层 - Shell 命令执行工具

提供安全的 shell 命令执行能力，支持工作目录设置、超时控制和输出限制。
"""

import asyncio
import logging
import os
from typing import Optional

from src.domain.entities.tool import ToolContext, ToolResult
from src.infrastructure.tools.decorator import tool

logger = logging.getLogger(__name__)


@tool(
    name="shell",
    description="Execute a shell command. Can be used to run scripts, query system info, install dependencies, etc. Note: dangerous commands may be blocked by security policy.",
    category="system",
    returns="Standard output and standard error of the command",
    timeout_ms=30000,
    max_calls_per_minute=30,
    sandboxed=True,
)
async def shell(
    command: str,
    working_dir: Optional[str] = None,
    timeout_ms: Optional[int] = None,
    context: Optional[ToolContext] = None,
) -> ToolResult:
    """Shell 命令执行工具

    Args:
        command: 要执行的 shell 命令
        working_dir: 工作目录（可选，默认使用 context.workspace 或当前目录）
        timeout_ms: 超时时间（毫秒），覆盖装饰器默认值
    """
    # 输入验证
    if not command.strip():
        return ToolResult(
            output="Error: command cannot be empty",
            success=False,
            error="invalid_input",
        )

    # 确定工作目录
    if working_dir:
        cwd = working_dir
    elif context and context.workspace:
        cwd = context.workspace
    else:
        cwd = os.getcwd()

    # 验证工作目录存在
    if not os.path.isdir(cwd):
        return ToolResult(
            output=f"Error: working directory does not exist: {cwd}",
            success=False,
            error="invalid_directory",
        )

    # 超时设置
    timeout_sec = (timeout_ms or 30000) / 1000.0

    try:
        logger.info("Executing shell command: %s (cwd=%s)", command, cwd)

        # 执行命令
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )

        # 等待完成（带超时）
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout_sec,
            )
        except asyncio.TimeoutError:
            # 超时后终止进程
            try:
                process.kill()
                await process.wait()
            except Exception:
                pass
            
            return ToolResult(
                output=f"Command timed out after {timeout_sec:.1f}s: {command}",
                success=False,
                error="timeout",
                metadata={
                    "command": command,
                    "cwd": cwd,
                    "timeout_ms": timeout_ms or 30000,
                },
            )

        # 解码输出（限制长度）
        stdout = _decode_output(stdout_bytes)
        stderr = _decode_output(stderr_bytes)

        # 限制输出长度（避免 context 爆炸）
        max_output_length = 10000
        stdout_truncated = False
        stderr_truncated = False

        if len(stdout) > max_output_length:
            stdout = stdout[:max_output_length] + "\n... [output truncated]"
            stdout_truncated = True

        if len(stderr) > max_output_length:
            stderr = stderr[:max_output_length] + "\n... [output truncated]"
            stderr_truncated = True

        # 构建输出
        output_parts = []
        if stdout:
            output_parts.append("## Standard Output")
            output_parts.append(stdout)
        
        if stderr:
            output_parts.append("## Standard Error")
            output_parts.append(stderr)

        output = "\n\n".join(output_parts) if output_parts else "(no output)"

        # 判断成功与否
        success = process.returncode == 0

        return ToolResult(
            output=output,
            success=success,
            metadata={
                "command": command,
                "cwd": cwd,
                "returncode": process.returncode,
                "stdout_length": len(stdout_bytes),
                "stderr_length": len(stderr_bytes),
                "stdout_truncated": stdout_truncated,
                "stderr_truncated": stderr_truncated,
            },
        )

    except Exception as e:
        logger.exception("Shell command failed")
        return ToolResult(
            output=f"Command execution failed: {e}",
            success=False,
            error=str(e),
            metadata={
                "command": command,
                "cwd": cwd,
            },
        )


def _decode_output(data: bytes) -> str:
    """解码命令输出，处理编码错误"""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return data.decode("latin-1")
        except Exception:
            return "(binary output)"
