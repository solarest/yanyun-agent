"""Shim: re-exports DomainEvent from the agent_loop subdomain.

The canonical DomainEvent definition lives in the agent_loop subdomain.
This module exists for backward compatibility.
"""

from src.domain.agent_loop.events_base import DomainEvent

__all__ = ["DomainEvent"]
