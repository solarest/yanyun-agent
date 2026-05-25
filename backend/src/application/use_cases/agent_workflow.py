"""应用层 - Agent 工作流路由函数

路由函数已提取到 domain/services/agent_routing.py，本模块保留为 re-export 兼容层。
AgentWorkflowBuilder 已移至 infrastructure/agent/workflow_builder.py。
"""

from src.domain.services.agent_routing import (
    route_after_llm,
    route_after_loop_detect,
    route_after_tool_execute,
)

__all__ = ["route_after_llm", "route_after_loop_detect", "route_after_tool_execute"]
