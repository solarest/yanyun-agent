"""Persist merged AgentState snapshots at graph execution boundaries."""

from pathlib import Path

from langgraph.types import RunnableConfig

from src.domain.services.checkpoint_serializer import serialize_agent_state


async def persist_state_node(
    state: dict, config: RunnableConfig | None = None
) -> dict:
    """Write the current AgentState snapshot without changing graph state."""
    configurable = (config or {}).get("configurable", {})
    storage = configurable.get("file_storage")
    task_dir = configurable.get("task_dir")
    if storage is not None and task_dir:
        pending_confirmation = state.get("pending_confirmation")
        storage.write_checkpoint(
            Path(task_dir),
            serialize_agent_state(state),
            state.get("current_turn", 0),
            resume_status=(
                "awaiting_confirmation" if pending_confirmation else "running"
            ),
            pending_confirmation=pending_confirmation,
        )
    return {}
