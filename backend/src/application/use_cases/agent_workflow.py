"""应用层 - Agent 工作流用例

职责:
1. 构建 Agent StateGraph(5 个核心节点)
2. 定义路由函数(纯判定,不修改 state)
3. 路由极简:llm_call 只做"有无 tool_calls"的二元判断,
   分类评估分别交给 loop_detect / stuck_detect

节点:llm_call / tool_execute / loop_detect / stuck_detect / context_compact
"""
import logging

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.domain.entities.agent_state import AgentState
from src.infrastructure.agent.nodes.context_compact_node import (
    context_compact_node,
)
from src.infrastructure.agent.nodes.llm_call_node import llm_call_node
from src.infrastructure.agent.nodes.loop_detect_node import loop_detect_node
from src.infrastructure.agent.nodes.stuck_detect_node import stuck_detect_node
from src.infrastructure.agent.nodes.tool_execute_node import tool_execute_node

logger = logging.getLogger(__name__)


# === 辅助函数 ===


def _extract_tool_calls(msg) -> list:
    """从消息中提取 tool_calls 列表"""
    try:
        if isinstance(msg, dict):
            return msg.get("tool_calls") or []
        elif hasattr(msg, "tool_calls"):
            return msg.tool_calls or []
        return []
    except Exception as e:
        logger.warning("Failed to extract tool_calls from message: %s", e)
        return []


# === 路由函数(纯判定,不修改 state) ===


def route_after_llm(state: AgentState) -> str:
    """LLM 调用后的路由决策

    极简三分支:
    1. should_end → END
    2. 有 tool_calls → loop_detect(先检测循环)
    3. 其他 → stuck_detect(文本评估+卡住检测)
    """
    if state.get("should_end"):
        return END

    messages = state.get("messages", [])
    if not messages:
        return END

    last_msg = messages[-1]
    tool_calls = _extract_tool_calls(last_msg)

    if tool_calls:
        return "loop_detect"  # 有 tool_calls，先检测循环

    return "stuck_detect"  # 纯文本进入 stuck_detect 评估


def route_after_loop_detect(state: AgentState) -> str:
    """Loop 检测后路由

    loop_detect_node 内部已处理反馈注入和升级策略:
    - 未检测到 → tool_execute
    - should_end → END(count >= 3 或预算耗尽)
    - count == 2 → context_compact(已设置 compression_strategy)
    - count < 2 → llm_call(已注入反馈消息)
    """
    if not state.get("loop_detected"):
        return "tool_execute"
    if state.get("should_end"):
        return END
    if state.get("loop_detection_count", 0) == 2:
        return "context_compact"
    return "llm_call"


def route_after_tool_execute(state: AgentState) -> str:
    """工具执行后路由

    - awaiting_user_input → END(等待用户确认)
    - 工具执行完毕 → llm_call(继续循环)
    """
    if state.get("awaiting_user_input"):
        return END

    # 工具执行完毕，回到 llm_call 继续
    return "llm_call"


def route_after_stuck_detect(state: AgentState) -> str:
    """Stuck 检测后路由

    stuck_detect_node 内部已处理反馈注入和升级策略:
    - should_end → END(count >= 3 或预算耗尽)
    - 其他 → llm_call(已注入反馈消息)
    """
    if state.get("should_end"):
        return END
    return "llm_call"


# === 工作流构建器 ===


class AgentWorkflowBuilder:
    """Agent StateGraph 构建器

    5 个核心节点,4 个条件路由 + 1 个固定边
    """

    _compiled: CompiledStateGraph | None = None

    @classmethod
    def build(cls) -> CompiledStateGraph:
        """构建并编译 StateGraph(单例缓存)"""
        if cls._compiled is not None:
            return cls._compiled

        workflow = StateGraph(AgentState)

        # === 核心节点(5 个) ===
        workflow.add_node("llm_call", llm_call_node)
        workflow.add_node("tool_execute", tool_execute_node)
        workflow.add_node("loop_detect", loop_detect_node)  # 吸收 tool_observe
        # 吸收 answer_observe
        workflow.add_node("stuck_detect", stuck_detect_node)
        workflow.add_node("context_compact", context_compact_node)

        # === 入口 ===
        workflow.set_entry_point("llm_call")

        # === LLM 后路由(三分支) ===
        workflow.add_conditional_edges(
            "llm_call",
            route_after_llm,
            {
                "loop_detect": "loop_detect",    # 有 tool_calls,先检测循环
                "stuck_detect": "stuck_detect",   # 纯文本,检测是否卡住
                END: END,                           # should_end=True
            },
        )

        # === Loop 检测后路由(四分支) ===
        workflow.add_conditional_edges(
            "loop_detect",
            route_after_loop_detect,
            {
                "tool_execute": "tool_execute",
                "llm_call": "llm_call",
                "context_compact": "context_compact",
                END: END,
            },
        )

        # === 工具执行后路由(两分支) ===
        workflow.add_conditional_edges(
            "tool_execute",
            route_after_tool_execute,
            {
                "llm_call": "llm_call",         # 工具执行完毕,继续循环
                END: END,                        # awaiting_user_input
            },
        )

        # === Stuck 检测后路由(两分支) ===
        workflow.add_conditional_edges(
            "stuck_detect",
            route_after_stuck_detect,
            {
                "llm_call": "llm_call",
                END: END,
            },
        )

        # === 固定边 ===
        workflow.add_edge("context_compact", "llm_call")

        cls._compiled = workflow.compile()
        return cls._compiled
