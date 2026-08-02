"""Tests for CheckpointResumeService — resume graph from checkpointer.json."""

import json
from pathlib import Path
from typing import Annotated, TypedDict

import pytest
from langgraph.graph import END, StateGraph
from langgraph.types import interrupt, Command

from src.infrastructure.agent.file_backed_saver import FileBackedSaver
from src.application.services.session_file_storage import SessionFileStorage


class _ResumeState(TypedDict):
    messages: Annotated[list, lambda x, y: x + y]
    pending_approval: bool
    approved: bool
    turn: int


def _step_with_interrupt(state):
    """If pending_approval and not yet approved, interrupt. Otherwise proceed."""
    if state["pending_approval"] and not state["approved"]:
        decision = interrupt("approve?")
        return {"approved": decision == "approve", "messages": [f"approved={decision}"], "turn": state["turn"] + 1}
    return {"messages": [f"turn_{state['turn'] + 1}"], "turn": state["turn"] + 1}


class TestCheckpointResumeService:
    """Tests for checkpoint-based resume."""

    def test_checkpointer_json_contains_writes_after_interrupt(self, tmp_path):
        """After graph interrupts, checkpointer.json should have writes."""
        file_path = str(tmp_path / "checkpointer.json")
        saver = FileBackedSaver(file_path=file_path)

        builder = StateGraph(_ResumeState)
        builder.add_node("step", _step_with_interrupt)
        builder.set_entry_point("step")
        builder.add_edge("step", END)

        graph = builder.compile(checkpointer=saver)
        config = {"configurable": {"thread_id": "t1"}}

        from langgraph.errors import GraphInterrupt
        try:
            graph.invoke(
                {"messages": [], "pending_approval": True, "approved": False, "turn": 0},
                config,
            )
        except GraphInterrupt:
            pass  # Expected

        # After interrupt, checkpointer.json should have writes
        assert Path(file_path).exists()
        data = json.loads(Path(file_path).read_text())
        assert "writes" in data
        assert len(data["writes"]) > 0

    def test_resume_after_load_continues_execution(self, tmp_path):
        """Loading checkpointer state and resuming with Command should work."""
        file_path = str(tmp_path / "checkpointer.json")
        saver = FileBackedSaver(file_path=file_path)

        builder = StateGraph(_ResumeState)
        builder.add_node("step", _step_with_interrupt)
        builder.set_entry_point("step")
        builder.add_edge("step", END)

        # First: interrupt the graph
        graph = builder.compile(checkpointer=saver)
        config = {"configurable": {"thread_id": "t1"}}
        state = {"messages": [], "pending_approval": True, "approved": False, "turn": 0}

        from langgraph.errors import GraphInterrupt
        try:
            graph.invoke(state, config)
        except GraphInterrupt:
            pass

        # Second: load from file, rebuild graph, resume with Command
        saver2 = FileBackedSaver(file_path=file_path)
        graph2 = builder.compile(checkpointer=saver2)

        result = graph2.invoke(Command(resume="approve"), config)
        assert result["approved"] is True

    def test_resume_after_restart_simulation(self, tmp_path):
        """Simulate restart: separate FileBackedSaver instances."""
        file_path = str(tmp_path / "checkpointer.json")

        # Phase 1: Run with saver1, interrupt
        saver1 = FileBackedSaver(file_path=file_path)
        builder1 = StateGraph(_ResumeState)
        builder1.add_node("step", _step_with_interrupt)
        builder1.set_entry_point("step")
        builder1.add_edge("step", END)
        graph1 = builder1.compile(checkpointer=saver1)
        config = {"configurable": {"thread_id": "t1"}}

        from langgraph.errors import GraphInterrupt
        try:
            graph1.invoke(
                {"messages": [], "pending_approval": True, "approved": False, "turn": 0},
                config,
            )
        except GraphInterrupt:
            pass

        # Phase 2: "Restart" — new saver, new graph, load from file
        saver2 = FileBackedSaver(file_path=file_path)
        builder2 = StateGraph(_ResumeState)
        builder2.add_node("step", _step_with_interrupt)
        builder2.set_entry_point("step")
        builder2.add_edge("step", END)
        graph2 = builder2.compile(checkpointer=saver2)

        result = graph2.invoke(Command(resume="approve"), config)
        assert result["approved"] is True
        assert result["turn"] == 1
