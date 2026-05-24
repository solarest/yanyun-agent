"""Web Fetch 工具单元测试"""

import os

import pytest

from src.domain.tool import ToolContext, ToolResult
from src.infrastructure.tools.builtin.web_fetch import web_fetch
from src.infrastructure.tools.decorator import clear_collected_tools


@pytest.fixture(autouse=True)
def _clean():
    clear_collected_tools()
    yield
    clear_collected_tools()


# === web_fetch 测试 ===


class TestWebFetch:
    @pytest.mark.asyncio
    async def test_empty_url(self) -> None:
        # 直接调用底层装饰后的函数
        rt = web_fetch._registered_tool  # type: ignore[attr-defined]
        result = await rt.func({"url": "   "}, None)
        assert result.success is False
        assert result.error == "invalid_input"

    @pytest.mark.asyncio
    async def test_invalid_url_format(self) -> None:
        rt = web_fetch._registered_tool  # type: ignore[attr-defined]
        result = await rt.func({"url": "not-a-valid-url"}, None)
        assert result.success is False
        assert result.error == "invalid_url"

    @pytest.mark.asyncio
    async def test_unsupported_scheme(self) -> None:
        rt = web_fetch._registered_tool  # type: ignore[attr-defined]
        result = await rt.func({"url": "ftp://example.com"}, None)
        assert result.success is False
        assert result.error == "unsupported_scheme"

    @pytest.mark.asyncio
    async def test_valid_url_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """测试成功获取网页内容（使用 mock）"""
        import httpx
        from unittest.mock import AsyncMock, MagicMock, patch

        # Mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html><body>Hello World</body></html>"
        mock_response.request = MagicMock()

        # Mock client
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch('httpx.AsyncClient', return_value=mock_client):
            rt = web_fetch._registered_tool  # type: ignore[attr-defined]
            result = await rt.func({"url": "https://example.com"}, None)

            assert result.success is True
            assert "https://example.com" in result.output
            assert "Hello World" in result.output
            assert result.metadata["url"] == "https://example.com"
            assert result.metadata["content_length"] > 0

    @pytest.mark.asyncio
    async def test_http_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """测试 HTTP 错误处理"""
        import httpx
        from unittest.mock import AsyncMock, MagicMock, patch

        # Mock 404 response
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.reason_phrase = "Not Found"
        mock_response.request = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch('httpx.AsyncClient', return_value=mock_client):
            rt = web_fetch._registered_tool  # type: ignore[attr-defined]
            result = await rt.func({"url": "https://example.com/not-found"}, None)

            assert result.success is False
            assert result.error == "network_error"
            assert "HTTP 404" in result.output

    @pytest.mark.asyncio
    async def test_content_truncation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """测试内容截断功能"""
        import httpx
        from unittest.mock import AsyncMock, MagicMock, patch

        # Create long content
        long_content = "<html><body>" + "A" * 15000 + "</body></html>"

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = long_content
        mock_response.request = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch('httpx.AsyncClient', return_value=mock_client):
            rt = web_fetch._registered_tool  # type: ignore[attr-defined]
            result = await rt.func({
                "url": "https://example.com",
                "max_length": 10000
            }, None)

            assert result.success is True
            assert result.metadata["truncated"] is True
            assert "[Content truncated]" in result.output
            # 验证内容被截断到指定长度附近
            assert result.metadata["content_length"] <= 10000 + \
                len("\n... [Content truncated]")
