"""Shim: re-exports from src.domain.agent_loop for backward compatibility.

Agent 工作流路由函数位于 domain/agent_loop/agent_routing.py，
AgentWorkflowBuilder 实现位于 infrastructure/agent_loop/workflow/builder.py。
"""

from src.domain.agent_loop.agent_routing import (
    route_after_llm,
    route_after_loop_detect,
    route_after_tool_execute,
)

__all__ = ["route_after_llm", "route_after_loop_detect", "route_after_tool_execute"]
