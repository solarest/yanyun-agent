"""Tests for SystemPromptBuilder

Covers:
- Prompt assembly via PromptAssembleService
- Mode branching: normal / sub-agent / team-mode
- Agent not found error
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.services.system_prompt_builder import SystemPromptBuilder


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_agent():
    """Create a mock Agent with minimal config."""
    agent = MagicMock()
    agent.id = "agent-1"
    agent.config = "{}"
    return agent


@pytest.fixture
def mock_agent_repo(mock_agent):
    """Mock IAgentRepository that returns mock_agent."""
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=mock_agent)
    return repo


# ─────────────────────────────────────────────────────────────────
# SystemPromptBuilder
# ─────────────────────────────────────────────────────────────────

class TestSystemPromptBuilder:
    """Tests for SystemPromptBuilder.build() and _apply_mode()"""

    @pytest.mark.asyncio
    async def test_build_raises_when_agent_not_found(self):
        """build() raises ValueError when agent does not exist"""
        repo = MagicMock()
        repo.get_by_id = AsyncMock(return_value=None)
        builder = SystemPromptBuilder(agent_repo=repo)

        with pytest.raises(ValueError, match="Agent unknown not found"):
            await builder.build(
                agent_id="unknown",
                workspace="/tmp",
            )

    @pytest.mark.asyncio
    async def test_build_calls_assemble_service_and_returns_system_prompt(self, mock_agent_repo):
        """build() assembles prompt and returns result for normal mode"""
        with patch(
            "src.application.services.system_prompt_builder.PromptAssembleService"
        ) as MockAssembleSvc:
            mock_assemble = MagicMock()
            mock_assemble.assemble.return_value = MagicMock(
                system_message="You are a helpful assistant.",
                layers=["layer1"],
                total_token_estimate=500,
                static_prefix_tokens=200,
            )
            MockAssembleSvc.return_value = mock_assemble

            with patch(
                "src.application.services.system_prompt_builder.PromptTemplate"
            ) as MockTemplate:
                mock_template = MagicMock()
                mock_template.memory_md = False
                MockTemplate.from_agent.return_value = mock_template

                builder = SystemPromptBuilder(agent_repo=mock_agent_repo)
                result = await builder.build(
                    agent_id="agent-1",
                    workspace="/tmp/ws",
                )

                assert result == "You are a helpful assistant."
                mock_assemble.assemble.assert_called_once()

    @pytest.mark.asyncio
    async def test_build_with_tool_registry_includes_tool_defs(self, mock_agent_repo):
        """build() passes tool_defs from ToolRegistry to assemble service"""
        tool_registry = MagicMock()
        tool_registry.get_tool_defs.return_value = [
            MagicMock(name="read_file"),
            MagicMock(name="write_file"),
        ]

        with patch(
            "src.application.services.system_prompt_builder.PromptAssembleService"
        ) as MockSvc:
            mock_assemble = MagicMock()
            mock_assemble.assemble.return_value = MagicMock(
                system_message="prompt with tools",
                layers=[],
                total_token_estimate=100,
                static_prefix_tokens=50,
            )
            MockSvc.return_value = mock_assemble

            with patch(
                "src.application.services.system_prompt_builder.PromptTemplate"
            ) as MockTpl:
                MockTpl.from_agent.return_value = MagicMock(memory_md=False)

                builder = SystemPromptBuilder(
                    agent_repo=mock_agent_repo,
                    tool_registry=tool_registry,
                )
                await builder.build(agent_id="agent-1", workspace="/tmp")

                # Verify tool_defs were passed
                call_args = mock_assemble.assemble.call_args
                assert "tools" in call_args[1]
                assert len(call_args[1]["tools"]) == 2


class TestApplyMode:
    """Tests for _apply_mode() mode branching"""

    def test_normal_mode_returns_assembled_prompt_unchanged(self):
        """_apply_mode() for normal (non-sub-agent, non-team) returns prompt as-is"""
        builder = SystemPromptBuilder(agent_repo=MagicMock())
        prompt = "system prompt"
        result = builder._apply_mode(
            prompt,
            is_sub_agent=False,
            parent_system_prompt=None,
            sub_agent_description=None,
            team_mode=False,
        )
        assert result == prompt

    def test_team_mode_returns_assembled_prompt_unchanged(self):
        """_apply_mode() for team_mode=True returns prompt unchanged"""
        builder = SystemPromptBuilder(agent_repo=MagicMock())
        prompt = "team system prompt"
        result = builder._apply_mode(
            prompt,
            is_sub_agent=True,
            parent_system_prompt="parent prompt",
            sub_agent_description="task desc",
            team_mode=True,
        )
        assert result == prompt

    def test_sub_agent_mode_delegates_to_orchestrator(self):
        """_apply_mode() for sub-agent mode uses SubAgentOrchestrator"""
        with patch(
            "src.domain.services.sub_agent_orchestrator.SubAgentOrchestrator"
        ) as MockOrch:
            mock_orch = MagicMock()
            mock_orch.build_sub_agent_system_prompt.return_value = "sub-agent prompt"
            MockOrch.return_value = mock_orch

            builder = SystemPromptBuilder(agent_repo=MagicMock())
            result = builder._apply_mode(
                "assembled prompt",
                is_sub_agent=True,
                parent_system_prompt="parent sys prompt",
                sub_agent_description="do X",
                team_mode=False,
            )

            assert result == "sub-agent prompt"
            mock_orch.build_sub_agent_system_prompt.assert_called_once_with(
                parent_system_prompt="parent sys prompt",
                description="do X",
            )
