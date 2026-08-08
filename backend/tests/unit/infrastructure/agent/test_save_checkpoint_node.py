"""Tests for save_checkpoint_node."""

import json
from pathlib import Path
from typing import Annotated, TypedDict
from unittest import mock

import pytest

from src.infrastructure.agent.file_backed_saver import FileBackedSaver


class _TestState(TypedDict):
    messages: Annotated[list, lambda x, y: x + y]
    turn: int


def _step(state):
    return {"messages": [f"turn_{state['turn'] + 1}"], "turn": state["turn"] + 1}


class TestSaveCheckpointNode:
    """Tests for save_checkpoint_node function."""

    def test_node_returns_empty_update(self, tmp_path):
        """Node should not modify AgentState."""
        from src.infrastructure.agent.save_checkpoint_node import save_checkpoint_node

        file_path = str(tmp_path / "checkpointer.json")
        state = {"messages": [], "turn": 0}
        config = {"configurable": {
            "thread_id": "t1", "checkpoint_ns": "",
            "checkpointer_file": file_path,
        }}

        result = save_checkpoint_node(state, config)
        assert result == {}

    def test_node_serializes_checkpointer_to_file(self, tmp_path):
        """When _default_checkpointer exists with state, node writes JSON."""
        from src.infrastructure.agent.save_checkpoint_node import save_checkpoint_node

        file_path = str(tmp_path / "checkpointer.json")
        saver = FileBackedSaver(file_path=file_path)

        # Run a graph to populate checkpointer state
        from langgraph.graph import StateGraph, END
        builder = StateGraph(_TestState)
        builder.add_node("step", _step)
        builder.set_entry_point("step")
        builder.add_edge("step", END)
        graph = builder.compile(checkpointer=saver)
        graph.invoke({"messages": [], "turn": 0},
                     {"configurable": {"thread_id": "t1"}})

        # Monkeypatch the _default_checkpointer imported in save_checkpoint_node
        import src.infrastructure.agent.save_checkpoint_node as node_mod
        with mock.patch.object(node_mod, "_default_checkpointer", return_value=saver):
            state = {"messages": [], "turn": 0}
            config = {"configurable": {
                "thread_id": "t1", "checkpoint_ns": "",
                "checkpointer_file": file_path,
            }}
            result = save_checkpoint_node(state, config)

        assert result == {}
        assert Path(file_path).exists()

        data = json.loads(Path(file_path).read_text())
        assert "storage" in data
        assert "t1" in data["storage"]
