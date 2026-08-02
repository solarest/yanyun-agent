"""Save checkpointer state before each LLM call.

This node is placed between context_compact and llm_call in the agent
workflow. It serializes the current MemorySaver state to checkpointer.json.
"""

import json
import logging
from pathlib import Path

from langgraph.types import RunnableConfig

from src.infrastructure.agent.file_backed_saver import _to_json_safe
from src.infrastructure.agent.workflow_builder import _default_checkpointer

logger = logging.getLogger(__name__)


def save_checkpoint_node(state: dict, config: RunnableConfig | None = None) -> dict:
    """Save the current checkpointer state to file.

    Reads ``checkpointer_file`` from ``config["configurable"]`` and
    serializes the checkpointer's internal state (storage, writes, blobs)
    to JSON at that path.

    This node does NOT modify AgentState.

    Args:
        state: Current AgentState (unused).
        config: LangGraph RunnableConfig.

    Returns:
        Empty dict (no state changes).
    """
    if config is None:
        return {}

    configurable = config.get("configurable", {})
    file_path = configurable.get("checkpointer_file")

    if not file_path:
        return {}

    try:
        saver = _default_checkpointer()

        data = _to_json_safe({
            "storage": dict(saver.storage),
            "writes": dict(saver.writes),
            "blobs": dict(saver.blobs),
        })

        p = Path(file_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False))
    except Exception:
        logger.exception("save_checkpoint_node: failed to persist checkpointer state")

    return {}
