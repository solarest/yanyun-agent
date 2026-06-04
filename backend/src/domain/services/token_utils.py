"""Shim: re-exports from src.domain.agent_loop for backward compatibility."""

from src.domain.agent_loop.token_utils import (  # noqa: F401
    count_tokens,
    estimate_context_tokens,
    is_context_limit_error,
    render_message,
    resolve_max_context_tokens,
)
