"""基础设施层 - Agent 工作流构建器实现

编译 LangGraph StateGraph，将领域层路由逻辑与基础设施层节点组合在一起。
使用 MemorySaver checkpointer 支持 interrupt() 暂停/恢复（人在回路确认）。

Topology: 3 节点 + 2 条件路由 + 1 固定边
  context_compact → llm_call → (tool_execute | END)
                        tool_execute → (context_compact | END)
"""

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.domain.aggregates.agent.agent_state import AgentState
from src.domain.interfaces.agent_workflow import IAgentWorkflowBuilder
from src.infrastructure.agent.nodes.context_compact_node import context_compact_node
from src.infrastructure.agent.nodes.llm_call_node import llm_call_node
from src.infrastructure.agent.nodes.tool_execute_node import tool_execute_node
from src.infrastructure.agent.persist_state_node import persist_state_node

from src.domain.services.agent_routing import (
    route_after_llm,
    route_after_tool_execute,
)


class AgentWorkflowBuilder(IAgentWorkflowBuilder):
    """Agent StateGraph 构建器 — 3 个核心节点, 2 个条件路由 + 1 个固定边"""

    _compiled: CompiledStateGraph | None = None

    @classmethod
    def build(cls) -> CompiledStateGraph:
        if cls._compiled is not None:
            return cls._compiled

        workflow = StateGraph(AgentState)

        workflow.add_node("llm_call", llm_call_node)
        workflow.add_node("tool_execute", tool_execute_node)
        workflow.add_node("context_compact", context_compact_node)
        workflow.add_node("persist_state", persist_state_node)

        # 入口: context_compact 作为每轮 LLM 前置守门
        workflow.set_entry_point("context_compact")

        workflow.add_conditional_edges(
            "llm_call",
            route_after_llm,
            {"tool_execute": "tool_execute", "context_compact": "context_compact", END: END},
        )

        workflow.add_conditional_edges(
            "persist_state",
            route_after_tool_execute,
            {"tool_execute": "tool_execute", "context_compact": "context_compact", END: END},
        )

        workflow.add_edge("context_compact", "llm_call")
        workflow.add_edge("tool_execute", "persist_state")

        cls._compiled = workflow.compile()
        return cls._compiled

    @classmethod
    def reset(cls) -> None:
        """重置编译缓存（测试用）。"""
        cls._compiled = None
