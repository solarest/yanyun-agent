"""Shim: re-exports from src.domain.agent for backward compatibility."""

from src.domain.agent.entity import Agent, CONFIG_FILES, MAX_CONFIG_LENGTH, MAX_VIBES_COUNT  # noqa: F401
from src.domain.aggregates.agent.agent_state import AgentState  # noqa: F401

__all__ = ["Agent", "AgentState", "CONFIG_FILES", "MAX_CONFIG_LENGTH", "MAX_VIBES_COUNT"]
