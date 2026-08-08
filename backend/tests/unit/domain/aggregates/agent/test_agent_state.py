"""Regression tests for AgentState message reducer semantics."""

from langchain_core.messages import HumanMessage, RemoveMessage

from src.domain.aggregates.agent.agent_state import add_messages


def test_add_messages_removes_message_for_remove_message_update() -> None:
    """A compaction RemoveMessage must delete the matching state message."""
    existing = [HumanMessage(content="obsolete", id="msg-obsolete")]

    merged = add_messages(existing, [RemoveMessage(id="msg-obsolete")])

    assert merged == []


def test_add_messages_assigns_ids_to_idless_messages() -> None:
    """Messages need stable IDs so compaction updates replace instead of duplicate."""
    merged = add_messages([], [HumanMessage(content="hello")])

    assert len(merged) == 1
    assert merged[0].id
