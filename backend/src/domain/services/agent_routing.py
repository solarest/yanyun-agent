"""Shim: re-exports from src.domain.agent_loop for backward compatibility."""

from src.domain.agent_loop.agent_routing import (  # noqa: F401
    route_after_llm,
    route_after_tool_execute,
)
