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

    - should_end → END
    - has tool_calls → loop_detect (先检测循环)
    - otherwise → END
    """
    if state.get("should_end"):
        return END

    messages = state.get("messages", [])
    if not messages:
        return END

    last_msg = messages[-1]
    tool_calls = _extract_tool_calls(last_msg)

    if tool_calls:
        return "loop_detect"
    return END


def route_after_loop_detect(state: AgentState) -> str:
    """Loop 检测后的路由决策

    - no loop detected → tool_execute
    - should_end → END
    - count == 2 → context_compact
    - count < 2 → llm_call (feedback injected)
    """
    if not state.get("loop_detected"):
        return "tool_execute"
    if state.get("should_end"):
        return END
    if state.get("loop_detection_count", 0) == 2:
        return "context_compact"
    return "llm_call"


def route_after_tool_execute(state: AgentState) -> str:
    """工具执行后的路由决策

    - awaiting_user_input → END
    - otherwise → llm_call
    """
    if state.get("awaiting_user_input"):
        return END
    return "llm_call"
