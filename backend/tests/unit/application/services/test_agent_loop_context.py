"""Tests for AgentLoopContext

Covers:
- _build_initial_state(): correct dict construction
- _build_event_emitter(): normal vs sub-agent proxy
- _build_llm(): LLM creation + tool binding
- _build_tool_registry(): sub-agent / team-leader / team-member / normal
- build_all(): integration of sub-components
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage

from src.application.services.agent_loop_context import AgentLoopContext


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

@pytest.fixture
def deps():
    """Create minimal dependency mocks for AgentLoopContext."""
    return {
        "agent_repo": MagicMock(),
        "llm_provider": MagicMock(),
        "prompt_context": MagicMock(),
        "message_repo": MagicMock(),
        "skill_repo": MagicMock(),
        "task_repo": MagicMock(),
        "session_repo": MagicMock(),
        "event_emitter": MagicMock(),
        "tool_registry": MagicMock(),
        "workflow_builder": MagicMock(),
    }


def _make_context(**overrides):
    """Build AgentLoopContext with default mocks overridden."""
    base = {
        "agent_repo": MagicMock(),
        "llm_provider": None,
        "prompt_context": None,
        "message_repo": MagicMock(),
        "skill_repo": None,
        "task_repo": None,
        "session_repo": None,
        "event_emitter": None,
        "tool_registry": None,
        "workflow_builder": None,
    }
    base.update(overrides)
    return AgentLoopContext(**base)


# ─────────────────────────────────────────────────────────────────
# _build_initial_state
# ─────────────────────────────────────────────────────────────────

class TestBuildInitialState:

    def test_constructs_full_state_dict(self):
        """_build_initial_state() produces a dict with all required keys"""
        task = MagicMock()
        task.id = "task-abc"

        messages = [HumanMessage(content="hello")]
        state = AgentLoopContext._build_initial_state(
            task=task,
            messages=messages,
            content="hello",
            model="opus",
            max_turns=100,
            workspace="/tmp/ws",
            system_prompt="You are helpful.",
            is_sub_agent=False,
            parent_task_id=None,
        )

        assert state["task_id"] == "task-abc"
        assert state["messages"] == messages
        assert state["user_message"] == "hello"
        assert state["workspace"] == "/tmp/ws"
        assert state["model"] == "opus"
        assert state["max_turns"] == 100
        assert state["current_turn"] == 0
        assert state["phase"] == "idle"
        assert state["should_end"] is False
        assert state["is_complete"] is False
        assert state["system_prompt"] == "You are helpful."
        assert state["is_sub_agent"] is False
        assert state["parent_task_id"] is None

    def test_sets_context_management_fields(self):
        """_build_initial_state() initializes context management fields"""
        task = MagicMock()
        task.id = "task-1"

        state = AgentLoopContext._build_initial_state(
            task=task,
            messages=[HumanMessage(content="hi")],
            content="hi",
            model="",
            max_turns=50,
            workspace="/tmp",
            system_prompt="sys",
            is_sub_agent=False,
            parent_task_id=None,
        )

        assert "max_context_tokens" in state
        assert state["max_context_tokens"] > 0
        assert state["context_token_estimate"] >= 0
        assert state["context_token_baseline"] is None
        assert state["context_token_baseline_message_count"] == 1
        assert state["context_compaction_attempts"] == 0
        assert state["emergency_compact_requested"] is False
        assert state["last_context_strategy"] is None

    def test_sets_sub_agent_fields(self):
        """_build_initial_state() tracks sub-agent fields"""
        task = MagicMock()
        task.id = "sub-task"

        state = AgentLoopContext._build_initial_state(
            task=task,
            messages=[],
            content="sub work",
            model="sonnet",
            max_turns=20,
            workspace="/tmp/sub",
            system_prompt="sub sys",
            is_sub_agent=True,
            parent_task_id="parent-task-1",
        )

        assert state["is_sub_agent"] is True
        assert state["parent_task_id"] == "parent-task-1"

    def test_tool_fields_initialized_empty(self):
        """_build_initial_state() initializes tool fields as empty"""
        task = MagicMock()
        task.id = "task-1"

        state = AgentLoopContext._build_initial_state(
            task=task,
            messages=[],
            content="",
            model="",
            max_turns=50,
            workspace="/tmp",
            system_prompt="",
            is_sub_agent=False,
            parent_task_id=None,
        )

        assert state["pending_tool_calls"] == []
        assert state["tool_results"] == {}
        assert state["awaiting_user_input"] is False
        assert state["last_executed_tool_call_ids"] == []
        assert state["final_result"] is None


# ─────────────────────────────────────────────────────────────────
# _build_event_emitter
# ─────────────────────────────────────────────────────────────────

class TestBuildEventEmitter:

    def test_normal_mode_returns_direct_emitter(self):
        """Normal (non-sub-agent) returns the direct event emitter"""
        emitter = MagicMock()
        ctx = _make_context(event_emitter=emitter)

        result = ctx._build_event_emitter(
            is_sub_agent=False,
            parent_task_id=None,
            sub_task_id=None,
        )
        assert result == emitter

    def test_sub_agent_mode_returns_proxy_emitter(self):
        """Sub-agent mode wraps emitter in ProxyEventEmitter"""
        with patch(
            "src.domain.services.ProxyEventEmitter"
        ) as MockProxy:
            mock_proxy = MagicMock()
            MockProxy.return_value = mock_proxy

            emitter = MagicMock()
            ctx = _make_context(event_emitter=emitter)

            result = ctx._build_event_emitter(
                is_sub_agent=True,
                parent_task_id="parent-1",
                sub_task_id="sub-1",
            )

            assert result == mock_proxy
            MockProxy.assert_called_once_with(
                emitter,
                parent_task_id="parent-1",
                sub_task_id="sub-1",
            )


# ─────────────────────────────────────────────────────────────────
# _build_llm
# ─────────────────────────────────────────────────────────────────

class TestBuildLLM:

    def test_raises_when_llm_provider_not_configured(self):
        """_build_llm() raises RuntimeError if llm_provider is None"""
        ctx = _make_context(llm_provider=None)

        with pytest.raises(RuntimeError, match="LLM Provider"):
            ctx._build_llm(
                model="opus",
                tool_registry=None,
                agent_id="agent-1",
            )

    def test_creates_chat_model_with_model_name(self):
        """_build_llm() calls llm_provider.create_chat_model()"""
        provider = MagicMock()
        provider.create_chat_model.return_value = MagicMock()
        ctx = _make_context(llm_provider=provider)

        ctx._build_llm(
            model="sonnet",
            tool_registry=None,
            agent_id="agent-1",
        )

        provider.create_chat_model.assert_called_with(model="sonnet")

    def test_binds_tools_when_tool_registry_has_tools(self):
        """_build_llm() binds tool schemas when registry has tools"""
        provider = MagicMock()
        llm = MagicMock()
        provider.create_chat_model.return_value = llm

        tool_registry = MagicMock()
        tool_registry.tool_count = 3

        with patch(
            "src.application.services.agent_loop_context.LangChainAdapter"
        ) as MockAdapter:
            MockAdapter.tool_defs_to_openai_functions.return_value = [
                {"type": "function", "function": {"name": "read"}}
            ]

            ctx = _make_context(llm_provider=provider, tool_registry=tool_registry)
            result = ctx._build_llm(
                model="opus",
                tool_registry=tool_registry,
                agent_id="agent-1",
            )

            llm.bind_tools.assert_called_once()

    def test_skips_tool_binding_when_no_tools(self):
        """_build_llm() does not bind tools when registry is empty"""
        provider = MagicMock()
        llm = MagicMock()
        provider.create_chat_model.return_value = llm

        tool_registry = MagicMock()
        tool_registry.tool_count = 0

        ctx = _make_context(llm_provider=provider, tool_registry=tool_registry)
        ctx._build_llm(
            model="opus",
            tool_registry=tool_registry,
            agent_id="agent-1",
        )

        llm.bind_tools.assert_not_called()


# ─────────────────────────────────────────────────────────────────
# _build_tool_registry
# ─────────────────────────────────────────────────────────────────

class TestBuildToolRegistry:

    def test_normal_mode_returns_original_registry(self):
        """Non-sub-agent, non-team returns the configured tool_registry"""
        registry = MagicMock()
        ctx = _make_context(tool_registry=registry)

        result = ctx._build_tool_registry(
            is_sub_agent=False,
            allowed_tools=None,
            team_mode=False,
            team_role=None,
        )
        assert result == registry

    def test_sub_agent_mode_delegates_to_orchestrator(self):
        """Sub-agent uses SubAgentOrchestrator to create filtered registry"""
        registry = MagicMock()

        with patch(
            "src.domain.services.sub_agent_orchestrator.SubAgentOrchestrator"
        ) as MockOrch:
            mock_orch = MagicMock()
            mock_orch.create_sub_agent_tool_registry.return_value = MagicMock()
            MockOrch.return_value = mock_orch

            ctx = _make_context(tool_registry=registry)
            ctx._build_tool_registry(
                is_sub_agent=True,
                allowed_tools=["read_file"],
                team_mode=False,
            )

            mock_orch.create_sub_agent_tool_registry.assert_called_once()


# ─────────────────────────────────────────────────────────────────
# build_all (integration)
# ─────────────────────────────────────────────────────────────────

class TestBuildAll:

    @pytest.mark.asyncio
    async def test_build_all_returns_graph_config_and_initial_state(self):
        """build_all() returns (graph, config, initial_state) tuple"""
        task = MagicMock()
        task.id = "task-1"

        provider = MagicMock()
        llm = MagicMock()
        provider.create_chat_model.return_value = llm

        workflow_builder = MagicMock()
        workflow_builder.build.return_value = MagicMock()

        ctx = _make_context(
            llm_provider=provider,
            workflow_builder=workflow_builder,
            event_emitter=MagicMock(),
        )

        # Patch sub-components
        ctx._prompt_builder = MagicMock()
        ctx._prompt_builder.build = AsyncMock(return_value="system prompt")
        ctx._history_loader = MagicMock()
        ctx._history_loader.load = AsyncMock(return_value=[
            HumanMessage(content="hello")
        ])

        graph, config, state = await ctx.build_all(
            agent_id="agent-1",
            session_id="sess-1",
            task=task,
            content="hello",
            model="opus",
            max_turns=50,
            workspace="/tmp",
        )

        assert graph is not None
        assert "configurable" in config
        assert state["task_id"] == "task-1"
        assert state["current_turn"] == 0
