"""Tests for FileBackedSaver — persistent MemorySaver with JSON serialization."""

import json
import tempfile
from pathlib import Path
from typing import Annotated, TypedDict

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph


class SimpleState(TypedDict):
    messages: Annotated[list, lambda x, y: x + y]
    turn: int


def _make_graph():
    """Build a simple test graph."""
    def step(state):
        return {"messages": [f"turn_{state['turn'] + 1}"], "turn": state["turn"] + 1}

    builder = StateGraph(SimpleState)
    builder.add_node("step", step)
    builder.set_entry_point("step")
    builder.add_edge("step", END)
    return builder


class TestFileBackedSaverInit:
    """Tests for initialization and file loading."""

    def test_initializes_empty_when_no_file(self, tmp_path):
        from src.infrastructure.agent.file_backed_saver import FileBackedSaver

        file_path = tmp_path / "checkpointer.json"
        saver = FileBackedSaver(file_path=str(file_path))

        # Should have empty state
        assert len(saver.storage) == 0
        assert len(saver.writes) == 0

    def test_loads_state_from_existing_file(self, tmp_path):
        from src.infrastructure.agent.file_backed_saver import FileBackedSaver

        file_path = tmp_path / "checkpointer.json"

        # First instance: create and save
        saver1 = FileBackedSaver(file_path=str(file_path))
        graph = _make_graph().compile(checkpointer=saver1)
        config = {"configurable": {"thread_id": "t1"}}
        graph.invoke({"messages": [], "turn": 0}, config)

        # Second instance: load from file
        saver2 = FileBackedSaver(file_path=str(file_path))

        # Should have same state
        assert "t1" in saver2.storage
        assert len(saver2.storage["t1"][""]) == len(saver1.storage["t1"][""])

    def test_none_path_skips_persistence(self):
        """When file_path is None, behaves like plain MemorySaver."""
        from src.infrastructure.agent.file_backed_saver import FileBackedSaver

        saver = FileBackedSaver(file_path=None)
        graph = _make_graph().compile(checkpointer=saver)
        config = {"configurable": {"thread_id": "t1"}}
        graph.invoke({"messages": [], "turn": 0}, config)

        assert len(saver.storage) > 0  # Works in memory
        # No file to check — just shouldn't crash


class TestFileBackedSaverPersist:
    """Tests for persistence behavior."""

    def test_put_persists_to_file(self, tmp_path):
        from src.infrastructure.agent.file_backed_saver import FileBackedSaver

        file_path = tmp_path / "checkpointer.json"
        saver = FileBackedSaver(file_path=str(file_path))
        graph = _make_graph().compile(checkpointer=saver)
        config = {"configurable": {"thread_id": "t1"}}
        graph.invoke({"messages": [], "turn": 0}, config)

        # File should exist and be valid JSON
        assert file_path.exists()
        data = json.loads(file_path.read_text())
        assert "storage" in data
        assert "writes" in data

    def test_writes_persisted_on_interrupt(self, tmp_path):
        from src.infrastructure.agent.file_backed_saver import FileBackedSaver

        file_path = tmp_path / "checkpointer.json"
        saver = FileBackedSaver(file_path=str(file_path))

        # Simulate writes being added (as LangGraph does on interrupt)
        saver.put_writes(
            {"configurable": {"thread_id": "t1", "checkpoint_ns": "", "checkpoint_id": "ckpt-1"}},
            [("messages", "pending_value")],
            task_id="task-1",
        )

        # File should now contain writes
        data = json.loads(file_path.read_text())
        assert len(data["writes"]) > 0

    def test_json_contains_base64_encoded_data(self, tmp_path):
        from src.infrastructure.agent.file_backed_saver import FileBackedSaver

        file_path = tmp_path / "checkpointer.json"
        saver = FileBackedSaver(file_path=str(file_path))
        graph = _make_graph().compile(checkpointer=saver)
        config = {"configurable": {"thread_id": "t1"}}
        graph.invoke({"messages": [], "turn": 0}, config)

        data = json.loads(file_path.read_text())
        # storage entries should have base64-encoded checkpoint data
        ns_data = data["storage"]["t1"][""]
        first_ckpt = list(ns_data.values())[0]
        # Value is [tagged_ckpt, tagged_meta, parent] — serialized as list
        assert isinstance(first_ckpt, list)
        assert len(first_ckpt) == 3  # [ckpt, meta, parent]
        # ckpt is [tag, base64_string]
        assert isinstance(first_ckpt[0], list)
        assert first_ckpt[0][0] in ("msgpack", "json", "empty")


class TestFileBackedSaverRoundTrip:
    """Tests for full save → load → resume cycle."""

    def test_round_trip_preserves_checkpoint_count(self, tmp_path):
        from src.infrastructure.agent.file_backed_saver import FileBackedSaver

        file_path = tmp_path / "checkpointer.json"

        # Save
        saver1 = FileBackedSaver(file_path=str(file_path))
        graph = _make_graph().compile(checkpointer=saver1)
        config = {"configurable": {"thread_id": "t1"}}
        graph.invoke({"messages": [], "turn": 0}, config)
        graph.invoke({"messages": [], "turn": 5}, config)

        # Load
        saver2 = FileBackedSaver(file_path=str(file_path))
        ckpt_count1 = len(saver1.storage["t1"][""])
        ckpt_count2 = len(saver2.storage["t1"][""])
        assert ckpt_count2 == ckpt_count1

    def test_round_trip_graph_resume_works(self, tmp_path):
        """After load, graph.ainvoke(state) should continue with loaded checkpointer."""
        from src.infrastructure.agent.file_backed_saver import FileBackedSaver

        file_path = tmp_path / "checkpointer.json"

        # First execution
        saver1 = FileBackedSaver(file_path=str(file_path))
        graph1 = _make_graph().compile(checkpointer=saver1)
        config = {"configurable": {"thread_id": "t1"}}
        result1 = graph1.invoke({"messages": [], "turn": 0}, config)
        assert result1["turn"] == 1

        # Simulate process restart: load from file, rebuild graph, continue
        saver2 = FileBackedSaver(file_path=str(file_path))
        graph2 = _make_graph().compile(checkpointer=saver2)
        # Pass loaded state to continue execution
        loaded_state = graph2.get_state(config).values
        result2 = graph2.invoke(loaded_state, config)
        assert result2["turn"] == 2  # Continued from turn 1
