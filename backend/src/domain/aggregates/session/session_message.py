"""Shim: re-exports from src.domain.session.message for backward compatibility."""

from src.domain.session.message import SessionMessage, SessionMessageRole, MessageStatus  # noqa: F401

__all__ = ["SessionMessage", "SessionMessageRole", "MessageStatus"]
