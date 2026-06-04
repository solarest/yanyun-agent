"""Token 工具函数单元测试"""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src.domain.services.token_utils import (
    count_tokens,
    estimate_context_tokens,
    is_context_limit_error,
    render_message,
    resolve_max_context_tokens,
)


# ── resolve_max_context_tokens ──────────────────────────────

@pytest.mark.parametrize(
    "model,expected",
    [
        ("gemini-3-pro", 2_000_000),
        ("gemini-3-pro-preview", 2_000_000),
        ("gpt-5.5", 1_000_000),
        ("gpt-5.4-mini", 1_000_000),
        ("claude-opus-4.7", 1_000_000),
        ("claude-opus-4.6-20250514", 1_000_000),
        ("qwen3-max", 1_000_000),
        ("deepseek-v4-pro", 1_000_000),
        ("gpt-4", 128_000),
        ("unknown-model", 128_000),
        ("", 128_000),
    ],
)
def test_resolve_max_context_tokens(model: str, expected: int) -> None:
    assert resolve_max_context_tokens(model) == expected


def test_resolve_max_context_tokens_case_insensitive() -> None:
    assert resolve_max_context_tokens("DeepSeek-V4-PRO") == 1_000_000
    assert resolve_max_context_tokens("GPT-5.5") == 1_000_000


# ── count_tokens ───────────────────────────────────────────

def test_count_tokens_english() -> None:
    tokens = count_tokens("hello world")
    # 11 chars * 0.25 = 2.75 → int = 2
    assert tokens == 2


def test_count_tokens_chinese() -> None:
    tokens = count_tokens("你好世界")
    # 4 chars * 1.5 = 6
    assert tokens == 6


def test_count_tokens_mixed() -> None:
    tokens = count_tokens("你好 world")
    # "你好" 2 chars * 1.5 = 3, " world" 6 chars * 0.25 = 1.5
    # total = 4.5 → int = 4
    assert tokens == 4


def test_count_tokens_empty() -> None:
    assert count_tokens("") == 0


# ── render_message ─────────────────────────────────────────

def test_render_system_message() -> None:
    result = render_message(SystemMessage(content="You are helpful"))
    assert "[SYSTEM]" in result
    assert "You are helpful" in result


def test_render_human_message() -> None:
    result = render_message(HumanMessage(content="Hello"))
    assert "[HUMAN]" in result
    assert "Hello" in result


def test_render_ai_message() -> None:
    result = render_message(AIMessage(content="I can help"))
    assert "[AI]" in result
    assert "I can help" in result


def test_render_ai_message_with_tool_calls() -> None:
    result = render_message(
        AIMessage(
            content="",
            tool_calls=[{"name": "search", "args": {"q": "hello"}, "id": "call-1"}],
        )
    )
    assert "[AI]" in result
    assert "[tool_calls:search]" in result


def test_render_tool_message() -> None:
    result = render_message(
        ToolMessage(content="result data", tool_call_id="call-1", name="search")
    )
    assert "[TOOL]" in result
    assert "[tool:search]" in result
    assert "[call_id:call-1]" in result
    assert "result data" in result


def test_render_dict_message() -> None:
    result = render_message(
        {"role": "assistant", "content": "done", "tool_calls": [{"name": "read", "args": {}}]}
    )
    assert "[ASSISTANT]" in result
    assert "[tool_calls:read]" in result
    assert "done" in result


def test_render_message_empty_content() -> None:
    result = render_message(HumanMessage(content=""))
    assert "[HUMAN]" in result


# ── estimate_context_tokens ────────────────────────────────

def test_estimate_no_baseline() -> None:
    msgs = [HumanMessage(content="hi"), AIMessage(content="hello")]
    est = estimate_context_tokens(msgs)
    # "hi" = 2 chars * 0.25 = 0.5 → 0, but actually "hi" is 2 chars = 0
    # "hello" = 5 chars * 0.25 = 1.25 → 1
    # Plus prefix overhead from render_message
    assert est > 0


def test_estimate_with_baseline_incremental() -> None:
    msgs = [HumanMessage(content="hi"), AIMessage(content="hello")]
    # baseline = 100 tokens for first 2 messages, then 2 new messages added
    all_msgs = msgs + [HumanMessage(content="new"), AIMessage(content="msg")]
    est = estimate_context_tokens(all_msgs, baseline=100, baseline_message_count=2)
    # Should be baseline + tokens for the 2 new messages
    new_only = sum(count_tokens(render_message(m)) for m in all_msgs[2:])
    assert est == 100 + new_only


def test_estimate_baseline_invalidated_by_remove() -> None:
    """If message count < baseline_message_count (RemoveMessage happened),
    fall back to full recalculation."""
    msgs = [HumanMessage(content="only one")]
    est = estimate_context_tokens(msgs, baseline=500, baseline_message_count=10)
    # current_count (1) < baseline_message_count (10) → full recalc
    assert est == sum(count_tokens(render_message(m)) for m in msgs)
    assert est < 500  # should not be baseline-based


def test_estimate_empty() -> None:
    assert estimate_context_tokens([]) == 0
    assert estimate_context_tokens([], baseline=100, baseline_message_count=0) == 0


# ── is_context_limit_error ─────────────────────────────────

@pytest.mark.parametrize(
    "error_text",
    [
        "context_length_exceeded: maximum 128000",
        "maximum context length is 200000 tokens",
        "context window exceeded",
        "input too long for model",
        "prompt is too long",
        "token limit reached",
        "request too large for processing",
    ],
)
def test_is_context_limit_error_positive(error_text: str) -> None:
    assert is_context_limit_error(Exception(error_text)) is True


@pytest.mark.parametrize(
    "error_text",
    [
        "rate limit exceeded",
        "timeout",
        "internal server error",
        "invalid api key",
        "",
    ],
)
def test_is_context_limit_error_negative(error_text: str) -> None:
    assert is_context_limit_error(Exception(error_text)) is False


def test_is_context_limit_error_case_insensitive() -> None:
    assert is_context_limit_error(Exception("Context_Length_Exceeded: limit reached")) is True
