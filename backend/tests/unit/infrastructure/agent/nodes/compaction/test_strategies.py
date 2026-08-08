"""Tests for compaction strategies (compaction-strategy spec)

Covers:
- Strategy chain priority ordering & execution
- CompactionResult.to_state_update() contract
- SkipStrategy, SoftPruneStrategy, MicroCompactStrategy, EmergencyCompactStrategy
- _default_strategies() factory
"""

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from src.infrastructure.agent.nodes.compaction import (
    CompactionResult,
    SkipStrategy,
    SoftPruneStrategy,
    MicroCompactStrategy,
    EmergencyCompactStrategy,
    _default_strategies,
)


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

def _make_state(**overrides):
    """Build a minimal AgentState-like dict for testing."""
    base = {
        "messages": [],
        "max_context_tokens": 128_000,
        "context_token_estimate": 0,
        "context_token_baseline": None,
        "context_token_baseline_message_count": 0,
        "context_compaction_attempts": 0,
        "emergency_compact_requested": False,
        "last_context_strategy": None,
        "current_turn": 0,
        "phase": "idle",
    }
    base.update(overrides)
    return base


def _msg(content: str, role: str = "user", msg_id: str | None = None) -> HumanMessage:
    """Create a message with optional id."""
    if role == "system":
        return SystemMessage(content=content, id=msg_id)
    if role == "tool":
        return ToolMessage(content=content, tool_call_id="tc1", id=msg_id)
    return HumanMessage(content=content, id=msg_id)


def _long_tool_msg(length: int = 25000) -> ToolMessage:
    """Create a ToolMessage with content exceeding SOFT_PRUNE_MIN_CONTENT_LENGTH."""
    return ToolMessage(
        content="x" * length,
        tool_call_id="tc_long",
        id="msg_long",
    )


# ─────────────────────────────────────────────────────────────────
# CompactionResult
# ─────────────────────────────────────────────────────────────────

class TestCompactionResult:
    """Spec: Strategy result contract"""

    def test_to_state_update_minimal(self):
        """to_state_update() produces correct dict for a basic result"""
        result = CompactionResult(
            strategy="skip",
            messages=[],
            token_estimate=5000,
            removed_count=0,
            baseline_invalidated=False,
        )
        update = result.to_state_update()
        assert update["phase"] == "context_compacting"
        assert update["context_token_estimate"] == 5000
        assert update["last_context_strategy"] == "skip"
        assert "context_token_baseline" not in update  # not invalidated

    def test_to_state_update_baseline_invalidated(self):
        """Spec: Soft-prune returns baseline_invalidated=True → sets baseline to None"""
        result = CompactionResult(
            strategy="soft_prune",
            messages=[],
            token_estimate=3000,
            removed_count=0,
            baseline_invalidated=True,
            pruned_count=5,
        )
        update = result.to_state_update()
        assert update["context_token_baseline"] is None
        assert update["context_token_baseline_message_count"] == 0

    def test_to_state_update_with_emergency_fields(self):
        """Emergency compact sets compaction_attempts and clear_emergency"""
        result = CompactionResult(
            strategy="emergency_compact",
            messages=[],
            token_estimate=1000,
            removed_count=20,
            baseline_invalidated=True,
            compaction_attempts=3,
            clear_emergency=True,
        )
        update = result.to_state_update()
        assert update["context_compaction_attempts"] == 3
        assert update["emergency_compact_requested"] is False


# ─────────────────────────────────────────────────────────────────
# _default_strategies factory
# ─────────────────────────────────────────────────────────────────

class TestDefaultStrategies:
    """Spec: Strategy chain evaluation by priority"""

    def test_strategies_sorted_by_priority_descending(self):
        """_default_strategies() returns strategies in descending priority order"""
        strategies = _default_strategies()
        priorities = [s.priority for s in strategies]
        assert priorities == sorted(priorities, reverse=True), \
            f"Expected descending order, got {priorities}"
        assert priorities == [3, 2, 1, 0]

    def test_strategy_types_correct(self):
        """_default_strategies() returns the expected strategy types"""
        strategies = _default_strategies()
        names = [s.name for s in strategies]
        assert names == ["emergency_compact", "micro_compact", "soft_prune", "skip"]


# ─────────────────────────────────────────────────────────────────
# SkipStrategy
# ─────────────────────────────────────────────────────────────────

class TestSkipStrategy:
    """Spec: SkipStrategy as fallback"""

    def test_should_apply_always_true(self):
        """SkipStrategy.should_apply() returns True regardless of state"""
        strategy = SkipStrategy()
        assert strategy.should_apply({}, [], 0, 128_000) is True
        assert strategy.should_apply({}, [], 100_000, 128_000) is True

    @pytest.mark.asyncio
    async def test_apply_returns_noop_result(self):
        """Spec: Skip returns baseline_invalidated=False, preserves all messages"""
        messages = [_msg("hello", msg_id="1"), _msg("world", msg_id="2")]
        state = _make_state(messages=messages)

        strategy = SkipStrategy()
        result = await strategy.apply(
            state, messages,
            current_tokens=5000, max_tokens=128_000,
            config={}, context=MagicMock(),
        )

        assert result.strategy == "skip"
        assert result.baseline_invalidated is False
        assert result.removed_count == 0
        assert len(result.messages) == 2

    def test_priority_is_0(self):
        assert SkipStrategy().priority == 0

    def test_name_is_skip(self):
        assert SkipStrategy().name == "skip"


# ─────────────────────────────────────────────────────────────────
# SoftPruneStrategy
# ─────────────────────────────────────────────────────────────────

class TestSoftPruneStrategy:
    """Spec: Soft-prune truncates long ToolMessages"""

    def test_should_apply_above_watermark(self):
        """should_apply() returns True when tokens > 40% of max"""
        strategy = SoftPruneStrategy()
        max_tokens = 128_000
        # 40% of 128000 = 51200
        assert strategy.should_apply({}, [], 60_000, max_tokens) is True

    def test_should_apply_below_watermark(self):
        """should_apply() returns False when tokens <= 40% of max"""
        strategy = SoftPruneStrategy()
        max_tokens = 128_000
        assert strategy.should_apply({}, [], 40_000, max_tokens) is False

    @pytest.mark.asyncio
    async def test_apply_prunes_long_tool_message(self):
        """long ToolMessage is truncated; baseline_invalidated=True"""
        strategy = SoftPruneStrategy()
        long_msg = _long_tool_msg(length=25000)
        messages = [_msg("system", role="system", msg_id="sys"), long_msg]
        state = _make_state(messages=messages)

        result = await strategy.apply(
            state, messages,
            current_tokens=60_000, max_tokens=128_000,
            config={}, context=MagicMock(),
        )

        assert result.strategy == "soft_prune"
        assert result.pruned_count >= 1
        assert result.baseline_invalidated is True

        # Check pruned content: head + notice + tail pattern
        pruned_content = result.messages[1].content
        assert "[... tool result soft-pruned" in pruned_content
        assert "middle omitted ...]" in pruned_content
        # Original long content should not be fully present
        assert "x" * 25000 not in pruned_content

    @pytest.mark.asyncio
    async def test_apply_short_tool_message_not_modified(self):
        """ToolMessage under MIN_CONTENT_LENGTH is left unchanged"""
        strategy = SoftPruneStrategy()
        short_msg = ToolMessage(content="short result", tool_call_id="tc_short")
        messages = [_msg("hi", msg_id="1"), short_msg]
        state = _make_state(messages=messages)

        result = await strategy.apply(
            state, messages,
            current_tokens=60_000, max_tokens=128_000,
            config={}, context=MagicMock(),
        )

        # Short message should be preserved as-is
        assert result.messages[1].content == "short result"

    @pytest.mark.asyncio
    async def test_apply_stops_when_below_target(self):
        """pruning stops early when token estimate drops below target (25%)"""
        strategy = SoftPruneStrategy()
        # One long message that, when pruned, drops below target
        messages = [
            _msg("system", role="system", msg_id="sys"),
            _long_tool_msg(length=25000),
        ]
        state = _make_state(messages=messages)
        # Current tokens above watermark but pruning one msg should suffice
        result = await strategy.apply(
            state, messages,
            current_tokens=60_000, max_tokens=128_000,
            config={}, context=MagicMock(),
        )
        # Should have pruned the one long message and stopped
        assert result.pruned_count == 1

    @pytest.mark.asyncio
    async def test_apply_preserves_messages_after_target_is_reached(self):
        """Stopping pruning must not drop the remaining tool-call round."""
        strategy = SoftPruneStrategy()
        messages = [
            _msg("system", role="system", msg_id="sys"),
            _long_tool_msg(length=25000),
            ToolMessage(
                content="second result",
                tool_call_id="tc_second",
                id="msg_second",
            ),
            ToolMessage(
                content="third result",
                tool_call_id="tc_third",
                id="msg_third",
            ),
            _msg("continue", msg_id="after_tools"),
        ]

        result = await strategy.apply(
            _make_state(messages=messages),
            messages,
            current_tokens=60_000,
            max_tokens=128_000,
            config={},
            context=MagicMock(),
        )

        assert [message.id for message in result.messages] == [
            "sys",
            "msg_long",
            "msg_second",
            "msg_third",
            "after_tools",
        ]
        assert result.messages[2].content == "second result"
        assert result.messages[3].content == "third result"

    def test_priority_is_1(self):
        assert SoftPruneStrategy().priority == 1


# ─────────────────────────────────────────────────────────────────
# MicroCompactStrategy
# ─────────────────────────────────────────────────────────────────

class TestMicroCompactStrategy:
    """Spec: Micro compact at 60% watermark"""

    def test_should_apply_above_60_percent(self):
        """should_apply() returns True when tokens > 60% of max"""
        strategy = MicroCompactStrategy()
        max_tokens = 128_000
        # 60% of 128000 = 76800
        assert strategy.should_apply({}, [], 80_000, max_tokens) is True

    def test_should_apply_below_60_percent(self):
        """should_apply() returns False when tokens <= 60% of max"""
        strategy = MicroCompactStrategy()
        max_tokens = 128_000
        assert strategy.should_apply({}, [], 70_000, max_tokens) is False

    def test_priority_is_2(self):
        assert MicroCompactStrategy().priority == 2

    @pytest.mark.asyncio
    async def test_apply_delegates_to_compact_messages(self):
        """MicroCompactStrategy.apply() delegates to compact_messages"""
        with patch(
            "src.infrastructure.agent.nodes.compaction.micro_compact.compact_messages"
        ) as mock_compact:
            mock_compact.return_value = CompactionResult(
                strategy="micro_compact",
                messages=[_msg("summary")],
                token_estimate=3000,
                removed_count=10,
                baseline_invalidated=True,
            )

            strategy = MicroCompactStrategy()
            messages = [_msg(f"msg-{i}", msg_id=str(i)) for i in range(20)]
            state = _make_state(messages=messages)

            result = await strategy.apply(
                state, messages,
                current_tokens=80_000, max_tokens=128_000,
                config={}, context=MagicMock(),
            )

            # Verify delegation
            mock_compact.assert_called_once()
            call_kwargs = mock_compact.call_args
            assert call_kwargs[1]["keep_recent"] == 10
            assert call_kwargs[1]["strategy"] == "micro_compact"
            assert result.strategy == "micro_compact"


# ─────────────────────────────────────────────────────────────────
# EmergencyCompactStrategy
# ─────────────────────────────────────────────────────────────────

class TestEmergencyCompactStrategy:
    """Spec: Emergency compaction takes precedence"""

    def test_should_apply_when_emergency_requested(self):
        """should_apply() checks emergency_compact_requested flag"""
        strategy = EmergencyCompactStrategy()
        state = _make_state(emergency_compact_requested=True)
        assert strategy.should_apply(state, [], 5_000, 128_000) is True

    def test_should_apply_false_when_no_emergency(self):
        """should_apply() returns False when emergency flag not set"""
        strategy = EmergencyCompactStrategy()
        state = _make_state(emergency_compact_requested=False)
        assert strategy.should_apply(state, [], 100_000, 128_000) is False

    def test_priority_is_3(self):
        assert EmergencyCompactStrategy().priority == 3

    @pytest.mark.asyncio
    async def test_apply_increments_compaction_attempts(self):
        """apply() increments compaction_attempts and sets clear_emergency"""
        with patch(
            "src.infrastructure.agent.nodes.compaction.emergency_compact.compact_messages"
        ) as mock_compact:
            mock_compact.return_value = CompactionResult(
                strategy="emergency_compact",
                messages=[_msg("emergency_summary")],
                token_estimate=1000,
                removed_count=30,
                baseline_invalidated=True,
            )

            strategy = EmergencyCompactStrategy()
            messages = [_msg(f"msg-{i}", msg_id=str(i)) for i in range(50)]
            state = _make_state(
                messages=messages,
                emergency_compact_requested=True,
                context_compaction_attempts=2,
            )

            result = await strategy.apply(
                state, messages,
                current_tokens=130_000, max_tokens=128_000,
                config={}, context=MagicMock(),
            )

            assert result.compaction_attempts == 3  # 2 + 1
            assert result.clear_emergency is True

            # Verify compact_messages was called with keep_recent=3
            call_kwargs = mock_compact.call_args
            assert call_kwargs[1]["keep_recent"] == 3
            assert call_kwargs[1]["strategy"] == "emergency_compact"

    @pytest.mark.asyncio
    async def test_apply_default_attempts_when_not_set(self):
        """apply() treats missing compaction_attempts as 0"""
        with patch(
            "src.infrastructure.agent.nodes.compaction.emergency_compact.compact_messages"
        ) as mock_compact:
            mock_compact.return_value = CompactionResult(
                strategy="emergency_compact",
                messages=[],
                token_estimate=500,
                removed_count=5,
                baseline_invalidated=True,
            )

            strategy = EmergencyCompactStrategy()
            state = _make_state(emergency_compact_requested=True)
            # context_compaction_attempts not set → default 0

            result = await strategy.apply(
                state, [],
                current_tokens=130_000, max_tokens=128_000,
                config={}, context=MagicMock(),
            )

            assert result.compaction_attempts == 1  # 0 + 1


# ─────────────────────────────────────────────────────────────────
# Strategy chain: priority traversal
# ─────────────────────────────────────────────────────────────────

class TestStrategyChainPriority:
    """Spec: Strategy chain evaluation by priority"""

    def test_first_match_wins(self):
        """When multiple strategies could match, only the first (highest priority) executes"""
        strategies = [
            EmergencyCompactStrategy(),
            MicroCompactStrategy(),
            SoftPruneStrategy(),
            SkipStrategy(),
        ]
        # At 80K tokens / 128K max = 62.5%:
        # - Emergency: no (no emergency flag)
        # - Micro: yes (62.5% > 60%)
        # - SoftPrune: yes (62.5% > 40%) — but should be skipped
        # - Skip: yes (always)
        state = _make_state()
        messages = [_msg("test", msg_id="1")]
        # current_tokens is the parameter strategies use, not state estimate
        current_tokens = 80_000
        max_tokens = state["max_context_tokens"]

        chosen = None
        for s in strategies:
            if s.should_apply(state, messages, current_tokens, max_tokens):
                chosen = s
                break

        assert chosen is not None
        assert chosen.name == "micro_compact", (
            f"Expected micro_compact (priority=2), got {chosen.name}"
        )

    def test_emergency_takes_precedence(self):
        """Spec: Emergency compaction takes precedence regardless of token count"""
        strategies = _default_strategies()
        state = _make_state(emergency_compact_requested=True)
        messages = [_msg("test", msg_id="1")]

        chosen = None
        for s in strategies:
            if s.should_apply(state, messages, 5_000, state["max_context_tokens"]):
                chosen = s
                break

        assert chosen is not None
        assert chosen.name == "emergency_compact", (
            f"Expected emergency_compact (priority=3), got {chosen.name}"
        )

    def test_skip_as_ultimate_fallback(self):
        """Spec: SkipStrategy as fallback — last in chain, always matches"""
        strategies = _default_strategies()
        state = _make_state()
        messages = [_msg("test", msg_id="1")]
        # 30K tokens / 128K max = 23.4% — below both 40% and 60% watermarks
        current_tokens = 30_000
        max_tokens = state["max_context_tokens"]

        chosen = None
        for s in strategies:
            if s.should_apply(state, messages, current_tokens, max_tokens):
                chosen = s
                break

        # At 30K tokens / 128K max = 23.4%:
        # Emergency: no | Micro: no (23% < 60%) | SoftPrune: no (23% < 40%)
        # Skip: yes (always)
        assert chosen is not None
        assert chosen.name == "skip", (
            f"Expected skip as fallback, got {chosen.name}"
        )
