"""应用层 - LangGraph StateGraph 构建器

职责：
1. 构建 Agent StateGraph
2. 定义节点和边
3. 定义路由函数
"""

from langgraph.graph import END, StateGraph
from langgraph.types import CompiledStateGraph

from src.domain.entities.agent_state import AgentState
from src.infrastructure.agent.nodes.complete_check_node import (
    is_claiming_complete,
)
from src.infrastructure.agent.nodes.context_compact_node import (
    context_compact_node,
)
from src.infrastructure.agent.nodes.llm_call_node import llm_call_node
from src.infrastructure.agent.nodes.loop_detect_node import loop_detect_node
from src.infrastructure.agent.nodes.stuck_detect_node import stuck_detect_node
from src.infrastructure.agent.nodes.tool_execute_node import tool_execute_node


def _inject_loop_feedback(state: AgentState) -> None:
    """注入 Loop 纠正反馈到消息历史"""
    state["messages"].append(
        {
            "role": "user",
            "content": (
                "WARNING: You seem to be repeating the same actions. "
                "Please try a different approach to solve the task. "
                "Analyze what went wrong and propose a new strategy."
            ),
        }
    )


def _inject_completion_feedback(state: AgentState) -> None:
    """注入完成纠正反馈"""
    state["messages"].append(
        {
            "role": "user",
            "content": (
                "You claimed the task is complete, but it appears there is still work to do. "
                "Please continue working on the task."
            ),
        }
    )


def route_after_llm(state: AgentState) -> str:
    """LLM 调用后的路由决策"""
    messages = state["messages"]
    if not messages:
        return END

    last_msg = messages[-1]

    # 检查是否有工具调用
    has_tool_calls = False
    if isinstance(last_msg, dict):
        has_tool_calls = bool(last_msg.get("tool_calls"))
    elif hasattr(last_msg, "tool_calls"):
        has_tool_calls = bool(last_msg.tool_calls)

    if has_tool_calls:
        return "loop_detect"

    # 纯文本响应
    text = ""
    if isinstance(last_msg, dict):
        text = last_msg.get("content", "")
    elif hasattr(last_msg, "content"):
        text = last_msg.content

    if is_claiming_complete(text):
        return "complete_check"

    # 检查是否为空或仅规划
    if not text.strip() or "let me think" in text.lower() or "here's a plan" in text.lower():
        state["messages"].append(
            {
                "role": "user",
                "content": "Now execute the plan or take action.",
            }
        )
        return "llm_call"

    # 检查是否需要用户输入
    # 简化：如果 LLM 直接问用户问题，结束循环
    if text.strip().endswith("?"):
        state["final_result"] = text
        return END

    return "llm_call"


def route_after_loop_detect(state: AgentState) -> str:
    """Loop 检测后的路由"""
    if not state.get("loop_detected"):
        return "tool_execute"

    count = state.get("loop_detection_count", 0)
    if count == 1:
        # 首次：注入反馈
        _inject_loop_feedback(state)
        return "llm_call"
    elif count == 2:
        # 二次：上下文压缩
        return "context_compact"
    else:
        # 三次：终止
        state["error"] = "Loop detected, terminating after 3 attempts"
        state["should_end"] = True
        return END


def route_after_complete_check(state: AgentState) -> str:
    """完成检查后的路由"""
    if state.get("is_complete"):
        state["phase"] = "completed"
        return END

    # 未完成，注入纠正
    _inject_completion_feedback(state)
    return "llm_call"


class AgentWorkflowBuilder:
    """Agent StateGraph 构建器"""

    def build(self) -> CompiledStateGraph:
        """构建并编译 StateGraph"""
        workflow = StateGraph(AgentState)

        # 添加节点
        workflow.add_node("llm_call", llm_call_node)
        workflow.add_node("tool_execute", tool_execute_node)
        workflow.add_node("loop_detect", loop_detect_node)
        workflow.add_node("stuck_detect", stuck_detect_node)
        workflow.add_node("context_compact", context_compact_node)
        workflow.add_node("complete_check", complete_check_node)

        # 设置入口点
        workflow.set_entry_point("llm_call")

        # LLM 后路由
        workflow.add_conditional_edges(
            "llm_call",
            route_after_llm,
            {
                "tool_execute": "tool_execute",
                "loop_detect": "loop_detect",
                "complete_check": "complete_check",
                "context_compact": "context_compact",
                "llm_call": "llm_call",
                END: END,
            },
        )

        # 工具执行后回到 LLM
        workflow.add_edge("tool_execute", "llm_call")

        # Loop 检测后路由
        workflow.add_conditional_edges(
            "loop_detect",
            route_after_loop_detect,
            {
                "llm_call": "llm_call",
                "context_compact": "context_compact",
                "tool_execute": "tool_execute",
                END: END,
            },
        )

        # 上下文压缩后回到 LLM
        workflow.add_edge("context_compact", "llm_call")

        # Stuck 检测后回到 LLM
        workflow.add_edge("stuck_detect", "llm_call")

        # 完成检查后路由
        workflow.add_conditional_edges(
            "complete_check",
            route_after_complete_check,
            {
                "llm_call": "llm_call",
                END: END,
            },
        )

        # 编译
        return workflow.compile()
