"""内置工具单元测试"""

import os
import types

import pytest

from src.domain.tool import ToolContext, ToolResult
from src.infrastructure.tools.builtin.web_search import (
    _format_tavily_results,
    web_search,
)
from src.infrastructure.tools.builtin.file_ops import file_read, file_search, file_write
from src.infrastructure.tools.builtin.clarify import clarify
from src.infrastructure.tools.decorator import clear_collected_tools


@pytest.fixture(autouse=True)
def _clean():
    clear_collected_tools()
    yield
    clear_collected_tools()


# === web_search 测试 ===


class TestWebSearch:
    @pytest.mark.asyncio
    async def test_empty_query(self) -> None:
        # 直接调用底层装饰后的函数
        rt = web_search._registered_tool  # type: ignore[attr-defined]
        result = await rt.func({"query": "   "}, None)
        assert result.success is False
        assert result.error == "invalid_input"

    @pytest.mark.asyncio
    async def test_missing_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        monkeypatch.setenv("SEARCH_PROVIDER", "tavily")
        rt = web_search._registered_tool  # type: ignore[attr-defined]
        result = await rt.func({"query": "test"}, None)
        assert result.success is False
        assert result.error == "config_missing"

    @pytest.mark.asyncio
    async def test_unsupported_provider(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SEARCH_PROVIDER", "unknown_provider")
        rt = web_search._registered_tool  # type: ignore[attr-defined]
        result = await rt.func({"query": "test"}, None)
        assert result.success is False
        assert result.error == "unsupported_provider"


class TestFormatTavilyResults:
    def test_with_answer_and_results(self) -> None:
        payload = {
            "answer": "Python is a programming language.",
            "results": [
                {
                    "title": "Python.org",
                    "url": "https://python.org",
                    "content": "The official site",
                    "score": 0.98,
                },
            ],
        }
        output = _format_tavily_results(payload)
        assert "## Summary" in output
        assert "Python is a programming language." in output
        assert "Python.org" in output
        assert "Relevance: 0.98" in output

    def test_empty_results(self) -> None:
        payload = {"results": [], "answer": None}
        output = _format_tavily_results(payload)
        assert output == "No results found."

    def test_results_without_answer(self) -> None:
        payload = {
            "results": [
                {"title": "Title", "url": "https://example.com", "content": "Content"},
            ],
        }
        output = _format_tavily_results(payload)
        assert "## Summary" not in output
        assert "## Search Results" in output
        assert "Title" in output

    def test_long_content_truncated(self) -> None:
        payload = {
            "results": [
                {"title": "T", "url": "", "content": "x" * 600},
            ],
        }
        output = _format_tavily_results(payload)
        assert "..." in output


# === file_ops 测试 ===


class TestFileRead:
    @pytest.mark.asyncio
    async def test_existing_file(self, tmp_path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("line1\nline2\nline3\n")
        rt = file_read._registered_tool  # type: ignore[attr-defined]
        result = await rt.func({"path": str(f)}, None)
        assert result.success is True
        assert "line1" in result.output
        assert result.metadata["total_lines"] == 3

    @pytest.mark.asyncio
    async def test_nonexistent_file(self) -> None:
        rt = file_read._registered_tool  # type: ignore[attr-defined]
        result = await rt.func({"path": "/nonexistent/file.txt"}, None)
        assert result.success is False
        assert result.error == "file_not_found"

    @pytest.mark.asyncio
    async def test_with_offset_limit(self, tmp_path) -> None:
        f = tmp_path / "lines.txt"
        f.write_text("\n".join(f"line{i}" for i in range(10)))
        rt = file_read._registered_tool  # type: ignore[attr-defined]
        result = await rt.func({"path": str(f), "offset": 2, "limit": 3}, None)
        assert result.success is True
        assert result.metadata["read_lines"] == 3

    @pytest.mark.asyncio
    async def test_blocks_workspace_escape(self, tmp_path) -> None:
        outside = tmp_path / "outside.txt"
        outside.write_text("secret")
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        ctx = ToolContext(task_id="t", workspace=str(workspace))
        rt = file_read._registered_tool  # type: ignore[attr-defined]
        result = await rt.func({"path": "../outside.txt"}, ctx)
        assert result.success is False
        assert result.error == "path_not_allowed"


class TestFileWrite:
    @pytest.mark.asyncio
    async def test_creates_file(self, tmp_path) -> None:
        target = tmp_path / "output.txt"
        rt = file_write._registered_tool  # type: ignore[attr-defined]
        result = await rt.func({"path": str(target), "content": "hello world"}, None)
        assert result.success is True
        assert target.read_text() == "hello world"

    @pytest.mark.asyncio
    async def test_creates_directories(self, tmp_path) -> None:
        target = tmp_path / "sub" / "dir" / "file.txt"
        rt = file_write._registered_tool  # type: ignore[attr-defined]
        result = await rt.func({"path": str(target), "content": "data"}, None)
        assert result.success is True
        assert target.exists()


class TestFileSearch:
    @pytest.mark.asyncio
    async def test_glob_pattern(self, tmp_path) -> None:
        (tmp_path / "a.py").write_text("python file")
        (tmp_path / "b.txt").write_text("text file")
        ctx = ToolContext(task_id="t", workspace=str(tmp_path))
        rt = file_search._registered_tool  # type: ignore[attr-defined]
        result = await rt.func({"pattern": "*.py"}, ctx)
        assert result.success is True
        assert "a.py" in result.output

    @pytest.mark.asyncio
    async def test_content_search(self, tmp_path) -> None:
        (tmp_path / "code.py").write_text("def hello():\n    pass\n")
        ctx = ToolContext(task_id="t", workspace=str(tmp_path))
        rt = file_search._registered_tool  # type: ignore[attr-defined]
        result = await rt.func(
            {"pattern": "*.py", "search_content": "hello"}, ctx
        )
        assert result.success is True
        assert "hello" in result.output

    @pytest.mark.asyncio
    async def test_blocks_pattern_escape(self, tmp_path) -> None:
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        rt = file_search._registered_tool  # type: ignore[attr-defined]
        result = await rt.func(
            {"pattern": "../*.py"},
            ToolContext(task_id="t", workspace=str(workspace)),
        )
        assert result.success is False
        assert "outside workspace" in result.output


# === clarify 测试 ===


class TestClarify:
    @pytest.mark.asyncio
    async def test_with_options(self) -> None:
        rt = clarify._registered_tool  # type: ignore[attr-defined]
        result = await rt.func(
            {"question": "Which DB?", "options": ["PostgreSQL", "MySQL"]}, None
        )
        assert result.success is True
        assert "Which DB?" in result.output
        assert "PostgreSQL" in result.output
        assert result.metadata["awaiting_user_input"] is True

    @pytest.mark.asyncio
    async def test_empty_question(self) -> None:
        rt = clarify._registered_tool  # type: ignore[attr-defined]
        result = await rt.func({"question": "   "}, None)
        assert result.success is False
        assert result.error == "invalid_input"

    @pytest.mark.asyncio
    async def test_without_options(self) -> None:
        rt = clarify._registered_tool  # type: ignore[attr-defined]
        result = await rt.func({"question": "What version?"}, None)
        assert result.success is True
        assert "Options" not in result.output
