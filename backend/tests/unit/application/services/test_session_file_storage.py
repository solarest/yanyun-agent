"""Tests for SessionFileStorage service."""

import json
import os
from pathlib import Path

import pytest

from src.application.services.session_file_storage import SessionFileStorage


class TestCreateTaskDir:
    """Tests for create_task_dir method."""

    def test_creates_directory_structure(self, tmp_path):
        storage = SessionFileStorage(base_path=str(tmp_path))
        session_id = "sess-001"
        task_id = "task-001"

        task_dir = storage.create_task_dir(session_id, task_id)

        expected = tmp_path / session_id / task_id
        assert task_dir == expected
        assert task_dir.is_dir()
        assert (task_dir / "events.jsonl").exists()
        assert (task_dir / "checkpoints").is_dir()
        assert (task_dir / "sub_agents").is_dir()
        assert (task_dir / "tool_results").is_dir()
        assert (task_dir / "meta.json").exists()

    def test_meta_json_contains_task_metadata(self, tmp_path):
        storage = SessionFileStorage(base_path=str(tmp_path))
        session_id = "sess-001"
        task_id = "task-001"

        task_dir = storage.create_task_dir(session_id, task_id)

        with open(task_dir / "meta.json") as f:
            meta = json.load(f)
        assert meta["session_id"] == session_id
        assert meta["task_id"] == task_id
        assert "created_at" in meta

    def test_idempotent_does_not_raise_on_existing_dir(self, tmp_path):
        storage = SessionFileStorage(base_path=str(tmp_path))
        session_id = "sess-001"
        task_id = "task-001"

        storage.create_task_dir(session_id, task_id)
        # Second call should not raise
        task_dir = storage.create_task_dir(session_id, task_id)
        assert task_dir.is_dir()


class TestAppendAndReadEvents:
    """Tests for append_event and read_events methods."""

    def test_append_event_writes_json_line(self, tmp_path):
        storage = SessionFileStorage(base_path=str(tmp_path))
        task_dir = storage.create_task_dir("sess-001", "task-001")
        event = {
            "seq": 1,
            "type": "task:started",
            "data": {"task_id": "task-001"},
        }

        storage.append_event(task_dir, event)

        # Read the file directly to verify
        with open(task_dir / "events.jsonl") as f:
            lines = f.readlines()
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["seq"] == 1
        assert parsed["type"] == "task:started"
        assert parsed["data"]["task_id"] == "task-001"
        assert "timestamp" in parsed

    def test_append_multiple_events_are_ordered(self, tmp_path):
        storage = SessionFileStorage(base_path=str(tmp_path))
        task_dir = storage.create_task_dir("sess-001", "task-001")

        for i in range(5):
            storage.append_event(task_dir, {"seq": i + 1, "type": f"event_{i}"})

        with open(task_dir / "events.jsonl") as f:
            lines = f.readlines()
        assert len(lines) == 5
        seqs = [json.loads(line)["seq"] for line in lines]
        assert seqs == [1, 2, 3, 4, 5]

    def test_read_events_returns_all_events(self, tmp_path):
        storage = SessionFileStorage(base_path=str(tmp_path))
        task_dir = storage.create_task_dir("sess-001", "task-001")

        for i in range(3):
            storage.append_event(task_dir, {"seq": i + 1, "type": f"event_{i}"})

        events = storage.read_events(task_dir)
        assert len(events) == 3
        assert events[0]["seq"] == 1
        assert events[2]["seq"] == 3

    def test_read_events_with_last_event_id(self, tmp_path):
        storage = SessionFileStorage(base_path=str(tmp_path))
        task_dir = storage.create_task_dir("sess-001", "task-001")

        for i in range(10):
            storage.append_event(
                task_dir, {"seq": i + 1, "type": f"event_{i}"}
            )

        events = storage.read_events(task_dir, last_event_id=5)
        assert len(events) == 5
        assert events[0]["seq"] == 6
        assert events[-1]["seq"] == 10

    def test_read_events_from_empty_file_returns_empty_list(self, tmp_path):
        storage = SessionFileStorage(base_path=str(tmp_path))
        task_dir = storage.create_task_dir("sess-001", "task-001")

        events = storage.read_events(task_dir)
        assert events == []

    def test_read_events_last_event_id_beyond_range_returns_empty(self, tmp_path):
        storage = SessionFileStorage(base_path=str(tmp_path))
        task_dir = storage.create_task_dir("sess-001", "task-001")

        for i in range(3):
            storage.append_event(task_dir, {"seq": i + 1, "type": f"event_{i}"})

        events = storage.read_events(task_dir, last_event_id=10)
        assert events == []


class TestUserMessage:
    """Tests for write_user_msg and read_user_msg methods."""

    def test_write_and_read_user_message(self, tmp_path):
        storage = SessionFileStorage(base_path=str(tmp_path))
        task_dir = storage.create_task_dir("sess-001", "task-001")
        message = {
            "role": "user",
            "content": "Hello, world!",
            "metadata": {"agent_id": "agent-1"},
        }

        storage.write_user_msg(task_dir, message)
        result = storage.read_user_msg(task_dir)

        assert result == message

    def test_read_user_msg_returns_none_when_file_missing(self, tmp_path):
        storage = SessionFileStorage(base_path=str(tmp_path))
        task_dir = storage.create_task_dir("sess-001", "task-001")

        result = storage.read_user_msg(task_dir)
        assert result is None


class TestCheckpoint:
    """Tests for write_checkpoint and read_latest_checkpoint methods."""

    def test_write_and_read_latest_checkpoint(self, tmp_path):
        storage = SessionFileStorage(base_path=str(tmp_path))
        task_dir = storage.create_task_dir("sess-001", "task-001")
        agent_state = {
            "messages": [],
            "tool_results": {},
            "turn_count": 3,
        }

        storage.write_checkpoint(task_dir, agent_state, turn_number=3)
        result = storage.read_latest_checkpoint(task_dir)

        assert result is not None
        assert result["state"]["messages"] == []
        assert result["state"]["turn_count"] == 3
        assert result["turn_number"] == 3

    def test_read_latest_checkpoint_returns_highest_turn(self, tmp_path):
        storage = SessionFileStorage(base_path=str(tmp_path))
        task_dir = storage.create_task_dir("sess-001", "task-001")

        for turn in [1, 2, 3]:
            storage.write_checkpoint(
                task_dir, {"turn": turn}, turn_number=turn
            )

        result = storage.read_latest_checkpoint(task_dir)
        assert result["turn_number"] == 3
        assert result["state"]["turn"] == 3

    def test_read_latest_checkpoint_returns_none_when_no_checkpoints(self, tmp_path):
        storage = SessionFileStorage(base_path=str(tmp_path))
        task_dir = storage.create_task_dir("sess-001", "task-001")

        result = storage.read_latest_checkpoint(task_dir)
        assert result is None

    def test_checkpoint_files_named_with_turn_number(self, tmp_path):
        storage = SessionFileStorage(base_path=str(tmp_path))
        task_dir = storage.create_task_dir("sess-001", "task-001")

        storage.write_checkpoint(task_dir, {"x": 1}, turn_number=5)

        ckpt_files = list((task_dir / "checkpoints").glob("turn_*.json"))
        assert len(ckpt_files) == 1
        assert ckpt_files[0].name == "turn_005.json"


class TestSubAgentDir:
    """Tests for sub-agent directory creation."""

    def test_creates_sub_agent_dir_under_parent(self, tmp_path):
        storage = SessionFileStorage(base_path=str(tmp_path))
        parent_dir = storage.create_task_dir("sess-001", "task-001")
        sub_task_id = "sub-task-001"

        sub_dir = storage.create_sub_agent_dir(parent_dir, sub_task_id)

        expected = parent_dir / "sub_agents" / sub_task_id
        assert sub_dir == expected
        assert sub_dir.is_dir()
        assert (sub_dir / "events.jsonl").exists()
        assert (sub_dir / "checkpoints").is_dir()

    def test_sub_agent_dir_registers_with_event_emitter(self, tmp_path):
        """After creating sub-agent dir, events should go to sub-agent file."""
        storage = SessionFileStorage(base_path=str(tmp_path))
        parent_dir = storage.create_task_dir("sess-001", "task-001")
        sub_dir = storage.create_sub_agent_dir(parent_dir, "sub-001")

        storage.append_event(sub_dir, {"seq": 1, "type": "sub:started"})

        events = storage.read_events(sub_dir)
        assert len(events) == 1
        assert events[0]["type"] == "sub:started"

        # Parent events should be separate
        parent_events = storage.read_events(parent_dir)
        assert len(parent_events) == 0


class TestToolResultFile:
    """Tests for write_tool_result_file method."""

    def test_writes_tool_result_to_dedicated_file(self, tmp_path):
        storage = SessionFileStorage(base_path=str(tmp_path))
        task_dir = storage.create_task_dir("sess-001", "task-001")
        tool_call_id = "call_abc123"
        output = "some large tool output content"

        file_path = storage.write_tool_result_file(task_dir, tool_call_id, output)

        expected = task_dir / "tool_results" / f"{tool_call_id}.txt"
        assert file_path == expected
        assert file_path.exists()
        assert file_path.read_text() == output

    def test_relative_path_in_result(self, tmp_path):
        storage = SessionFileStorage(base_path=str(tmp_path))
        task_dir = storage.create_task_dir("sess-001", "task-001")

        file_path = storage.write_tool_result_file(task_dir, "call_xyz", "content")

        # The returned path should be relative to the task directory
        expected_rel = Path("tool_results/call_xyz.txt")
        assert file_path.relative_to(task_dir) == expected_rel
