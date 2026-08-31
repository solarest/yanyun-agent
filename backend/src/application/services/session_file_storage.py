"""Session file storage service for process state persistence."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path


class SessionFileStorage:
    """Manages per-task local file storage for agent execution process state.

    Directory structure:
        <base_path>/<session_id>/<task_id>/
        ├── events.jsonl
        ├── checkpoints/
        │   └── turn_NNN.json
        ├── user_msg.json
        ├── meta.json
        ├── sub_agents/
        └── tool_results/
    """

    def __init__(self, base_path: str = "storage/sessions"):
        self.base_path = Path(base_path)

    # ── task directory ──────────────────────────────────────────────

    def create_task_dir(self, session_id: str, task_id: str) -> Path:
        """Create the task directory structure. Idempotent."""
        task_dir = self.base_path / session_id / task_id
        task_dir.mkdir(parents=True, exist_ok=True)

        (task_dir / "checkpoints").mkdir(exist_ok=True)
        (task_dir / "sub_agents").mkdir(exist_ok=True)
        (task_dir / "tool_results").mkdir(exist_ok=True)

        # events.jsonl — touch if missing
        events_path = task_dir / "events.jsonl"
        if not events_path.exists():
            events_path.touch()

        # meta.json — write if missing (don't overwrite)
        meta_path = task_dir / "meta.json"
        if not meta_path.exists():
            meta = {
                "session_id": session_id,
                "task_id": task_id,
                "created_at": datetime.now(UTC).isoformat(),
            }
            meta_path.write_text(json.dumps(meta, indent=2))

        return task_dir

    # ── events ──────────────────────────────────────────────────────

    def append_event(self, task_dir: Path, event: dict) -> None:
        """Append an event dict as a JSON line to events.jsonl."""
        event_with_ts = {**event, "timestamp": datetime.now(UTC).isoformat()}
        line = json.dumps(event_with_ts, ensure_ascii=False)
        with open(task_dir / "events.jsonl", "a") as f:
            f.write(line + "\n")

    def read_events(
        self, task_dir: Path, last_event_id: int | None = None
    ) -> list[dict]:
        """Read events from events.jsonl, optionally after a given seq number."""
        events_path = task_dir / "events.jsonl"
        if not events_path.exists():
            return []

        events: list[dict] = []
        with open(events_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                event = json.loads(line)
                if last_event_id is not None and event.get("seq", 0) <= last_event_id:
                    continue
                events.append(event)
        return events

    # ── user message ─────────────────────────────────────────────────

    def write_user_msg(self, task_dir: Path, message: dict) -> None:
        """Write user message to user_msg.json."""
        (task_dir / "user_msg.json").write_text(
            json.dumps(message, ensure_ascii=False, indent=2)
        )

    def read_user_msg(self, task_dir: Path) -> dict | None:
        """Read user message from user_msg.json. Returns None if missing."""
        path = task_dir / "user_msg.json"
        if not path.exists():
            return None
        return json.loads(path.read_text())

    # ── checkpoints ──────────────────────────────────────────────────

    def write_checkpoint(
        self,
        task_dir: Path,
        state: dict,
        turn_number: int,
        *,
        resume_status: str = "running",
        pending_confirmation: dict | None = None,
    ) -> Path:
        """Atomically save a recoverable AgentState snapshot for a turn."""
        ckpt_dir = task_dir / "checkpoints"
        filename = f"turn_{turn_number:03d}.json"
        ckpt_path = ckpt_dir / filename
        temporary_path = ckpt_path.with_suffix(".json.tmp")
        content = {
            "turn_number": turn_number,
            "saved_at": datetime.now(UTC).isoformat(),
            "resume_status": resume_status,
            "pending_confirmation": pending_confirmation,
            "state": state,
        }
        with open(temporary_path, "w", encoding="utf-8") as file:
            json.dump(content, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        temporary_path.replace(ckpt_path)
        return ckpt_path

    def read_latest_checkpoint(self, task_dir: Path) -> dict | None:
        """Read the newest valid checkpoint, skipping incomplete snapshots."""
        ckpt_dir = task_dir / "checkpoints"
        files = sorted(ckpt_dir.glob("turn_*.json"), reverse=True)
        for path in files:
            try:
                return json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
        return None

    # ── sub-agent ────────────────────────────────────────────────────

    def create_sub_agent_dir(self, parent_task_dir: Path, sub_task_id: str) -> Path:
        """Create a sub-agent directory under the parent task directory.

        Structure: <parent>/sub_agents/<sub_task_id>/
        """
        sub_dir = parent_task_dir / "sub_agents" / sub_task_id
        sub_dir.mkdir(parents=True, exist_ok=True)
        (sub_dir / "checkpoints").mkdir(exist_ok=True)
        events_path = sub_dir / "events.jsonl"
        if not events_path.exists():
            events_path.touch()
        return sub_dir

    # ── tool results ─────────────────────────────────────────────────

    def write_tool_result_file(
        self, task_dir: Path, tool_call_id: str, output: str
    ) -> Path:
        """Write complete tool output to a dedicated file. Returns the file path."""
        result_dir = task_dir / "tool_results"
        file_path = result_dir / f"{tool_call_id}.txt"
        file_path.write_text(output)
        return file_path
