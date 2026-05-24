"""基础设施层 - 文件操作工具

提供 file_read、file_write、file_search 三个工具。
"""

import glob as glob_module
import os
from typing import Optional

from src.domain.tool import ToolContext, ToolResult
from src.infrastructure.tools.decorator import tool


@tool(
    name="file_read",
    description="读取指定路径的文件内容。支持文本文件。",
    category="file",
    returns="文件内容文本",
    timeout_ms=10000,
)
async def file_read(
    path: str,
    offset: int = 0,
    limit: int = 2000,
    context: Optional[ToolContext] = None,
) -> ToolResult:
    """读取文件内容

    Args:
        path: 文件路径（相对于 workspace 或绝对路径）
        offset: 起始行号（从 0 开始）
        limit: 读取的最大行数
    """
    workspace = context.workspace if context else ""
    try:
        full_path = _resolve_path(path, workspace)
    except ValueError as e:
        return ToolResult(output=f"Access denied: {e}", success=False, error="path_not_allowed")

    if not os.path.isfile(full_path):
        return ToolResult(
            output=f"File not found: {path}",
            success=False,
            error="file_not_found",
        )

    try:
        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        total_lines = len(lines)
        selected = lines[offset : offset + limit]
        content = "".join(selected)

        header = (
            f"File: {path} "
            f"(lines {offset + 1}-{min(offset + limit, total_lines)} "
            f"of {total_lines})\n"
        )
        return ToolResult(
            output=header + content,
            metadata={"total_lines": total_lines, "read_lines": len(selected)},
        )
    except Exception as e:
        return ToolResult(output=f"Error reading file: {e}", success=False, error=str(e))


@tool(
    name="file_write",
    description="写入内容到指定文件。如果文件不存在则创建，存在则覆盖。",
    category="file",
    returns="写入结果确认",
    timeout_ms=10000,
)
async def file_write(
    path: str,
    content: str,
    context: Optional[ToolContext] = None,
) -> ToolResult:
    """写入文件

    Args:
        path: 文件路径
        content: 要写入的文件内容
    """
    workspace = context.workspace if context else ""
    try:
        full_path = _resolve_path(path, workspace)
    except ValueError as e:
        return ToolResult(output=f"Access denied: {e}", success=False, error="path_not_allowed")

    try:
        dir_name = os.path.dirname(full_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)

        return ToolResult(
            output=f"Successfully wrote {len(content)} characters to {path}",
            metadata={"bytes_written": len(content.encode("utf-8"))},
        )
    except Exception as e:
        return ToolResult(output=f"Error writing file: {e}", success=False, error=str(e))


@tool(
    name="file_search",
    description="在工作目录中搜索文件。支持 glob 模式匹配文件名，或在文件内容中搜索关键词。",
    category="file",
    returns="匹配的文件路径列表或包含关键词的行",
    timeout_ms=15000,
)
async def file_search(
    pattern: str,
    search_content: Optional[str] = None,
    max_results: int = 20,
    context: Optional[ToolContext] = None,
) -> ToolResult:
    """文件搜索

    Args:
        pattern: glob 模式（如 "**/*.py"）用于匹配文件名
        search_content: 在匹配文件中搜索的关键词（可选）
        max_results: 最大返回结果数
    """
    workspace = context.workspace if context else os.getcwd()

    try:
        search_path = _resolve_search_pattern(pattern, workspace)
        matches = glob_module.glob(search_path, recursive=True)
        matches = matches[:max_results]

        if search_content and matches:
            content_matches: list[str] = []
            for fpath in matches:
                if os.path.isfile(fpath):
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                            for i, line in enumerate(f, 1):
                                if search_content in line:
                                    rel = os.path.relpath(fpath, workspace)
                                    content_matches.append(f"{rel}:{i}: {line.rstrip()}")
                    except (OSError, UnicodeDecodeError):
                        continue

            output = "\n".join(content_matches[:max_results]) or "No content matches found."
        else:
            rel_paths = [os.path.relpath(m, workspace) for m in matches]
            output = "\n".join(rel_paths) or "No files found matching pattern."

        return ToolResult(output=output, metadata={"match_count": len(matches)})
    except Exception as e:
        return ToolResult(output=f"Search error: {e}", success=False, error=str(e))


def _resolve_path(path: str, workspace: str) -> str:
    """解析文件路径"""
    if os.path.isabs(path):
        resolved = os.path.abspath(path)
    else:
        resolved = os.path.abspath(os.path.join(workspace, path)) if workspace else os.path.abspath(path)

    if workspace:
        workspace_root = os.path.abspath(workspace)
        if os.path.commonpath([resolved, workspace_root]) != workspace_root:
            raise ValueError(f"path '{path}' is outside workspace '{workspace}'")

    return resolved


def _resolve_search_pattern(pattern: str, workspace: str) -> str:
    """解析并校验 glob 搜索模式。"""
    if workspace:
        if os.path.isabs(pattern):
            raise ValueError("absolute patterns are not allowed when workspace is set")
        normalized = os.path.normpath(pattern)
        if normalized.startswith(".."):
            raise ValueError(f"pattern '{pattern}' is outside workspace '{workspace}'")
        return os.path.join(workspace, normalized)
    return os.path.abspath(pattern)
