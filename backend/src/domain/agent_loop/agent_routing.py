"""领域层 - Agent 工作流路由函数

纯判定逻辑，不修改 state，不依赖基础设施层。
"""

import logging

from langgraph.graph import END

from src.domain.aggregates.agent.agent_state import AgentState

logger = logging.getLogger(__name__)


def _extract_tool_calls(msg) -> list:
    try:
        if isinstance(msg, dict):
            return msg.get("tool_calls") or []
        elif hasattr(msg, "tool_calls"):
            return msg.tool_calls or []
        return []
    except Exception as e:
        logger.warning("Failed to extract tool_calls from message: %s", e)
        return []


def route_after_llm(state: AgentState) -> str:
    """LLM 调用后的路由决策

    - emergency_compact_requested → context_compact (紧急压缩优先)
    - should_end → END
    - has tool_calls → tool_execute (直接路由，不再经过 loop_detect)
    - otherwise → END
    """
    if state.get("emergency_compact_requested"):
        return "context_compact"

    if state.get("should_end"):
        return END

    messages = state.get("messages", [])
    if not messages:
        return END

    last_msg = messages[-1]
    tool_calls = _extract_tool_calls(last_msg)

    if tool_calls:
        return "tool_execute"
    return END


def route_after_tool_execute(state: AgentState) -> str:
    """工具执行后的路由决策

    - awaiting_user_input → END
    - otherwise → context_compact (每轮 LLM 调用前都经过上下文守门)
    """
    if state.get("awaiting_user_input"):
        return END
    return "context_compact"
