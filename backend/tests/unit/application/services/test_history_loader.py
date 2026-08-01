"""Tests for HistoryLoader

Covers 5 loading modes:
- sub-agent: single HumanMessage only
- team-mode leader: session history, no inbound message
- team-mode member: session history + inbound message append
- with prompt_context: token-budgeted history
- fallback (without prompt_context): simple history
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.application.services.history_loader import HistoryLoader
from src.domain.aggregates.session.session_message import SessionMessageRole


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

def _history_msg(role: SessionMessageRole, content: str):
    """Create a mock session history message."""
    msg = MagicMock()
    msg.role = role
    msg.content = content
    msg.tool_calls = []
    return msg


@pytest.fixture
def message_repo():
    """Mock ISessionMessageRepository."""
    return MagicMock()


@pytest.fixture
def prompt_context():
    """Mock PromptContextInterface."""
    return MagicMock()


# ─────────────────────────────────────────────────────────────────
# HistoryLoader
# ─────────────────────────────────────────────────────────────────

class TestSubAgentMode:
    """Sub-agent: only the current task message, no session history"""

    @pytest.mark.asyncio
    async def test_load_returns_single_human_message(self, message_repo):
        """sub-agent mode returns exactly [HumanMessage(content=content)]"""
        loader = HistoryLoader(message_repo=message_repo, prompt_context=None)

        messages = await loader.load(
            session_id="sess-1",
            system_prompt="sys prompt",
            model="opus",
            content="do sub task",
            is_sub_agent=True,
        )

        assert len(messages) == 1
        assert isinstance(messages[0], HumanMessage)
        assert messages[0].content == "do sub task"


class TestTeamModeLeader:
    """Team mode leader: loads history from own session, no inbound message append"""

    @pytest.mark.asyncio
    async def test_load_does_not_append_inbound_message(self, message_repo, prompt_context):
        """Leader does not get the content appended as extra HumanMessage"""
        message_repo.list_by_session = AsyncMock(return_value=[
            _history_msg(SessionMessageRole.USER, "hello"),
        ])
        prompt_context.build_messages = AsyncMock(return_value=[
            {"role": "user", "content": "hello"},
        ])

        with patch(
            "src.application.services.history_loader.ConversationAssemblyService"
        ) as MockAsm:
            MockAsm.assemble.return_value = MagicMock()

            with patch(
                "src.application.services.history_loader.LangChainAdapter"
            ) as MockAdapter:
                MockAdapter.dict_messages_to_langchain.return_value = [
                    HumanMessage(content="hello")
                ]

                loader = HistoryLoader(
                    message_repo=message_repo,
                    prompt_context=prompt_context,
                )

                messages = await loader.load(
                    session_id="sess-1",
                    system_prompt="sys",
                    model="opus",
                    content="inbound msg",
                    team_mode=True,
                    team_role="leader",
                )

                # Leader: content is now appended in load() for deferred message persistence
                assert len(messages) == 2
                assert messages[0].content == "hello"
                assert messages[1].content == "inbound msg"


class TestTeamModeMember:
    """Team mode member: loads history + appends inbound message"""

    @pytest.mark.asyncio
    async def test_load_appends_inbound_message(self, message_repo, prompt_context):
        """Member gets the content as an extra HumanMessage at the end"""
        message_repo.list_by_session = AsyncMock(return_value=[])
        prompt_context.build_messages = AsyncMock(return_value=[])

        with patch(
            "src.application.services.history_loader.ConversationAssemblyService"
        ) as MockAsm:
            MockAsm.assemble.return_value = MagicMock()

            with patch(
                "src.application.services.history_loader.LangChainAdapter"
            ) as MockAdapter:
                MockAdapter.dict_messages_to_langchain.return_value = []

                loader = HistoryLoader(
                    message_repo=message_repo,
                    prompt_context=prompt_context,
                )

                messages = await loader.load(
                    session_id="sess-1",
                    system_prompt="sys",
                    model="opus",
                    content="inbound task",
                    team_mode=True,
                    team_role="member",
                )

                assert len(messages) == 1
                assert isinstance(messages[0], HumanMessage)
                assert messages[0].content == "inbound task"


class TestFallbackMode:
    """Fallback: simple history loading when no prompt_context"""

    @pytest.mark.asyncio
    async def test_load_without_prompt_context(self, message_repo):
        """Without prompt_context, uses fallback path"""
        message_repo.list_by_session = AsyncMock(return_value=[
            _history_msg(SessionMessageRole.USER, "hi"),
            _history_msg(SessionMessageRole.ASSISTANT, "Hi! How can I help?"),
        ])

        loader = HistoryLoader(message_repo=message_repo, prompt_context=None)
        messages = await loader.load(
            session_id="sess-1",
            system_prompt="sys",
            model="opus",
            content="new msg",
            is_sub_agent=False,
        )

        # Current user message appended at end (deferred persistence from file)
        assert len(messages) == 3
        assert isinstance(messages[0], HumanMessage)
        assert messages[0].content == "hi"
        assert isinstance(messages[1], AIMessage)
        assert messages[1].content == "Hi! How can I help?"
        assert isinstance(messages[2], HumanMessage)
        assert messages[2].content == "new msg"

    @pytest.mark.asyncio
    async def test_load_fallback_handles_tool_summary_role(self, message_repo):
        """Fallback converts TOOL_SUMMARY → HumanMessage with prefix"""
        message_repo.list_by_session = AsyncMock(return_value=[
            _history_msg(SessionMessageRole.TOOL_SUMMARY, "files modified: a.py"),
        ])

        loader = HistoryLoader(message_repo=message_repo, prompt_context=None)
        messages = await loader.load(
            session_id="sess-1",
            system_prompt="sys",
            model="opus",
            content="new",
            is_sub_agent=False,
        )

        # Current user message appended at end
        assert len(messages) == 2
        assert isinstance(messages[0], HumanMessage)
        assert messages[0].content == "[Tool Results] files modified: a.py"
        assert isinstance(messages[1], HumanMessage)
        assert messages[1].content == "new"

    @pytest.mark.asyncio
    async def test_load_fallback_appends_tool_names_to_assistant(self, message_repo):
        """Fallback appends tool names to AIMessage content when tool_calls present"""
        msg = _history_msg(SessionMessageRole.ASSISTANT, "Let me check.")
        msg.tool_calls = [
            {"name": "read_file", "args": {}},
            {"name": "search", "args": {}},
        ]

        message_repo.list_by_session = AsyncMock(return_value=[msg])

        loader = HistoryLoader(message_repo=message_repo, prompt_context=None)
        messages = await loader.load(
            session_id="sess-1",
            system_prompt="sys",
            model="opus",
            content="new",
            is_sub_agent=False,
        )

        # Current user message appended at end
        assert len(messages) == 2
        assert isinstance(messages[0], AIMessage)
        assert "[Used Tools: read_file, search]" in messages[0].content
        assert isinstance(messages[1], HumanMessage)
        assert messages[1].content == "new"


class TestPromptContextMode:
    """With prompt_context: token-budgeted history loading"""

    @pytest.mark.asyncio
    async def test_load_with_prompt_context(self, message_repo, prompt_context):
        """With prompt_context, uses _load_with_prompt_context path"""
        message_repo.list_by_session = AsyncMock(return_value=[
            _history_msg(SessionMessageRole.USER, "hello"),
        ])
        prompt_context.build_messages = AsyncMock(return_value=[
            {"role": "user", "content": "hello"},
        ])

        with patch(
            "src.application.services.history_loader.ConversationAssemblyService"
        ) as MockAsm:
            MockAsm.assemble.return_value = MagicMock()

            with patch(
                "src.application.services.history_loader.LangChainAdapter"
            ) as MockAdapter:
                MockAdapter.dict_messages_to_langchain.return_value = [
                    HumanMessage(content="hello")
                ]

                loader = HistoryLoader(
                    message_repo=message_repo,
                    prompt_context=prompt_context,
                )

                messages = await loader.load(
                    session_id="sess-1",
                    system_prompt="sys",
                    model="opus",
                    content="new msg",
                )

                # Current user message appended at end
                assert len(messages) == 2
                assert messages[0].content == "hello"
                assert messages[1].content == "new msg"
                prompt_context.build_messages.assert_called_once()
