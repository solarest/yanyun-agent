"""基础设施层 - Agent 工作流构建器实现

编译 LangGraph StateGraph，将领域层路由逻辑与基础设施层节点组合在一起。
使用 MemorySaver checkpointer 支持 interrupt() 暂停/恢复（人在回路确认）。

Topology: 3 节点 + 2 条件路由 + 1 固定边
  context_compact → llm_call → (tool_execute | END)
                        tool_execute → (context_compact | END)
"""

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.domain.aggregates.agent.agent_state import AgentState
from src.domain.interfaces.agent_workflow import IAgentWorkflowBuilder
from src.infrastructure.agent.nodes.context_compact_node import context_compact_node
from src.infrastructure.agent.nodes.llm_call_node import llm_call_node
from src.infrastructure.agent.nodes.tool_execute_node import tool_execute_node

from src.domain.services.agent_routing import (
    route_after_llm,
    route_after_tool_execute,
)


_checkpointer_singleton: MemorySaver | None = None


def _default_checkpointer() -> MemorySaver:
    """进程级单例 MemorySaver——确保初始执行与恢复使用同一实例。"""
    global _checkpointer_singleton
    if _checkpointer_singleton is None:
        _checkpointer_singleton = MemorySaver()
    return _checkpointer_singleton


class AgentWorkflowBuilder(IAgentWorkflowBuilder):
    """Agent StateGraph 构建器 — 3 个核心节点, 2 个条件路由 + 1 个固定边"""

    _compiled: CompiledStateGraph | None = None

    @classmethod
    def build(cls) -> CompiledStateGraph:
        if cls._compiled is not None:
            return cls._compiled

        workflow = StateGraph(AgentState)

        from src.infrastructure.agent.save_checkpoint_node import save_checkpoint_node

        workflow.add_node("llm_call", llm_call_node)
        workflow.add_node("tool_execute", tool_execute_node)
        workflow.add_node("context_compact", context_compact_node)
        workflow.add_node("save_checkpoint", save_checkpoint_node)

        # 入口: context_compact 作为每轮 LLM 前置守门
        workflow.set_entry_point("context_compact")

        workflow.add_conditional_edges(
            "llm_call",
            route_after_llm,
            {"tool_execute": "tool_execute", "context_compact": "context_compact", END: END},
        )

        workflow.add_conditional_edges(
            "tool_execute",
            route_after_tool_execute,
            {"tool_execute": "tool_execute", "context_compact": "context_compact", END: END},
        )

        # context_compact → save_checkpoint → llm_call
        # Checkpointer state is persisted before each LLM invocation
        workflow.add_edge("context_compact", "save_checkpoint")
        workflow.add_edge("save_checkpoint", "llm_call")

        cls._compiled = workflow.compile(checkpointer=_default_checkpointer())
        return cls._compiled

    @classmethod
    def build_with_checkpointer(cls, checkpointer):
        """Build a graph with a specific checkpointer (for checkpoint resume).

        Does NOT use the cached compiled graph — always recompiles.
        """
        from src.infrastructure.agent.save_checkpoint_node import save_checkpoint_node

        workflow = StateGraph(AgentState)
        workflow.add_node("llm_call", llm_call_node)
        workflow.add_node("tool_execute", tool_execute_node)
        workflow.add_node("context_compact", context_compact_node)
        workflow.add_node("save_checkpoint", save_checkpoint_node)
        workflow.set_entry_point("context_compact")
        workflow.add_conditional_edges(
            "llm_call", route_after_llm,
            {"tool_execute": "tool_execute", "context_compact": "context_compact", END: END},
        )
        workflow.add_conditional_edges(
            "tool_execute", route_after_tool_execute,
            {"tool_execute": "tool_execute", "context_compact": "context_compact", END: END},
        )
        workflow.add_edge("context_compact", "save_checkpoint")
        workflow.add_edge("save_checkpoint", "llm_call")
        return workflow.compile(checkpointer=checkpointer)

    @classmethod
    def reset(cls) -> None:
        """重置编译缓存（测试用）。"""
        cls._compiled = None
        global _checkpointer_singleton
        _checkpointer_singleton = None
