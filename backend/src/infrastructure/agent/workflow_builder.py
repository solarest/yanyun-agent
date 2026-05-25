"""基础设施层 - Agent 工作流构建器实现

编译 LangGraph StateGraph，将领域层路由逻辑与基础设施层节点组合在一起。
"""

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.domain.aggregates.agent.agent_state import AgentState
from src.domain.interfaces.agent_workflow import IAgentWorkflowBuilder
from src.infrastructure.agent.nodes.context_compact_node import context_compact_node
from src.infrastructure.agent.nodes.llm_call_node import llm_call_node
from src.infrastructure.agent.nodes.loop_detect_node import loop_detect_node
from src.infrastructure.agent.nodes.tool_execute_node import tool_execute_node

from src.domain.services.agent_routing import (
    route_after_llm,
    route_after_loop_detect,
    route_after_tool_execute,
)


class AgentWorkflowBuilder(IAgentWorkflowBuilder):
    """Agent StateGraph 构建器 — 4 个核心节点, 3 个条件路由 + 1 个固定边"""

    _compiled: CompiledStateGraph | None = None

    @classmethod
    def build(cls) -> CompiledStateGraph:
        if cls._compiled is not None:
            return cls._compiled

        workflow = StateGraph(AgentState)

        workflow.add_node("llm_call", llm_call_node)
        workflow.add_node("tool_execute", tool_execute_node)
        workflow.add_node("loop_detect", loop_detect_node)
        workflow.add_node("context_compact", context_compact_node)

        workflow.set_entry_point("llm_call")

        workflow.add_conditional_edges(
            "llm_call",
            route_after_llm,
            {"loop_detect": "loop_detect", END: END},
        )

        workflow.add_conditional_edges(
            "loop_detect",
            route_after_loop_detect,
            {"tool_execute": "tool_execute", "llm_call": "llm_call",
             "context_compact": "context_compact", END: END},
        )

        workflow.add_conditional_edges(
            "tool_execute",
            route_after_tool_execute,
            {"llm_call": "llm_call", END: END},
        )

        workflow.add_edge("context_compact", "llm_call")

        cls._compiled = workflow.compile()
        return cls._compiled
