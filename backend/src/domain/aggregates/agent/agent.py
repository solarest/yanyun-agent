"""Shim: re-exports from src.domain.agent.entity for backward compatibility."""

from src.domain.agent.entity import Agent, CONFIG_FILES, MAX_CONFIG_LENGTH, MAX_VIBES_COUNT  # noqa: F401

__all__ = ["Agent", "CONFIG_FILES", "MAX_CONFIG_LENGTH", "MAX_VIBES_COUNT"]
