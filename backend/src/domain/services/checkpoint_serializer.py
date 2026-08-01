"""AgentState checkpoint serialization.

Converts AgentState between in-memory form (with LangChain message objects)
and a JSON-serializable dict for file storage.
"""

from typing import Any

from langchain_core.messages import message_to_dict, messages_from_dict


def serialize_agent_state(state: dict) -> dict:
    """Serialize AgentState for file storage.

    Converts LangChain message objects in ``messages`` to dicts so the
    entire state can be JSON-serialized.
    """
    serialized: dict[str, Any] = {}
    for key, value in state.items():
        if key == "messages":
            serialized[key] = [message_to_dict(m) for m in value]
        else:
            serialized[key] = value
    return serialized


def deserialize_agent_state(serialized: dict) -> dict:
    """Restore AgentState from a serialized dict.

    Converts message dicts back to LangChain message objects.
    """
    state: dict[str, Any] = {}
    for key, value in serialized.items():
        if key == "messages":
            state[key] = messages_from_dict(value)
        else:
            state[key] = value
    return state
