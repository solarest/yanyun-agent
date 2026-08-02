"""File-backed MemorySaver with JSON persistence.

Extends MemorySaver to persist checkpoint state (storage, writes, blobs)
to a JSON file after each write operation. msgpack binary data is stored
as base64-encoded strings for JSON compatibility.
"""

import base64
import json
import logging
from pathlib import Path
from typing import Any

from langgraph.checkpoint.memory import MemorySaver

logger = logging.getLogger(__name__)


def _encode_tagged(tagged: tuple) -> list:
    """Encode a (tag, bytes) tuple to [tag, base64_string]."""
    tag, data = tagged
    return [tag, base64.b64encode(data).decode("ascii")]


def _decode_tagged(encoded: list) -> tuple:
    """Decode [tag, base64_string] back to (tag, bytes)."""
    tag, b64 = encoded
    return (tag, base64.b64decode(b64))


def _is_tagged(value: Any) -> bool:
    """Check if value is a (tag, bytes) pair from serde.dumps_typed()."""
    return (
        isinstance(value, tuple)
        and len(value) == 2
        and isinstance(value[0], str)
        and isinstance(value[1], bytes)
    )


def _to_json_safe(value: Any) -> Any:
    """Recursively convert MemorySaver internal data to JSON-safe types."""
    if _is_tagged(value):
        return _encode_tagged(value)
    if isinstance(value, tuple):
        return [_to_json_safe(v) for v in value]
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for k, v in value.items():
            str_key = "||".join(str(x) for x in k) if isinstance(k, tuple) else str(k)
            result[str_key] = _to_json_safe(v)
        return result
    if isinstance(value, list):
        return [_to_json_safe(v) for v in value]
    return value


def _from_json_safe(value: Any) -> Any:
    """Recursively convert JSON-safe types back to MemorySaver internal data."""
    if isinstance(value, list) and len(value) == 2 and all(isinstance(v, str) for v in value):
        # Could be encoded tagged value [tag, base64_string]
        return _decode_tagged(value) if value[0] in ("msgpack", "json", "empty", "null") else value
    if isinstance(value, list):
        return [_from_json_safe(v) for v in value]
    if isinstance(value, dict):
        result: dict = {}
        for str_key, v in value.items():
            key = tuple(str_key.split("||")) if "||" in str_key else str_key
            result[key] = _from_json_safe(v)
        return result
    return value


class FileBackedSaver(MemorySaver):
    """MemorySaver that persists checkpoint state to a JSON file.

    Storage format (checkpointer.json):
    .. code-block:: json

        {
          "storage": {
            "thread_id": {
              "": {
                "ckpt_id": {
                  "ckpt": ["msgpack", "<base64>"],
                  "meta": ["msgpack", "<base64>"],
                  "parent": "parent_id"
                }
              }
            }
          },
          "writes": {
            "thread_id||ns||ckpt_id": {
              "task_id||idx": ["task_id", "channel", ["msgpack", "<base64>"], "trigger"]
            }
          },
          "blobs": {
            "thread_id||ns||channel||version": ["msgpack", "<base64>"]
          }
        }
    """

    def __init__(self, *, file_path: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self._file_path = Path(file_path) if file_path else None
        if self._file_path and self._file_path.exists():
            self._load()

    # ── persistence ──────────────────────────────────────────────────

    def _save(self) -> None:
        """Serialize storage, writes, blobs to JSON file."""
        if self._file_path is None:
            return
        data = _to_json_safe({
            "storage": dict(self.storage),
            "writes": dict(self.writes),
            "blobs": dict(self.blobs),
        })
        try:
            self._file_path.parent.mkdir(parents=True, exist_ok=True)
            self._file_path.write_text(json.dumps(data, ensure_ascii=False))
        except Exception:
            logger.exception("Failed to save checkpointer state to %s", self._file_path)

    def _load(self) -> None:
        """Restore storage, writes, blobs from JSON file."""
        try:
            data = json.loads(self._file_path.read_text())
            loaded = _from_json_safe(data)
            for thread_key, ns_dict in loaded.get("storage", {}).items():
                self.storage[thread_key].update(ns_dict)
            for key, value in loaded.get("writes", {}).items():
                self.writes[key] = value
            for key, value in loaded.get("blobs", {}).items():
                self.blobs[key] = value
        except Exception:
            logger.exception("Failed to load checkpointer state from %s", self._file_path)

    # ── overrides ─────────────────────────────────────────────────────

    def put(self, config, checkpoint, metadata, new_versions):
        result = super().put(config, checkpoint, metadata, new_versions)
        self._save()
        return result

    async def aput(self, config, checkpoint, metadata, new_versions):
        result = await super().aput(config, checkpoint, metadata, new_versions)
        self._save()
        return result

    def put_writes(self, config, writes, task_id, task_path=""):
        super().put_writes(config, writes, task_id, task_path)
        self._save()
