"""Shim: re-exports from src.domain.session.entity for backward compatibility."""

from src.domain.session.entity import Session, SessionStatus  # noqa: F401

__all__ = ["Session", "SessionStatus"]
