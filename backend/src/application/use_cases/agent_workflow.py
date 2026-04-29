"""应用层 - Agent 工作流用例

职责：
1. 构建 Agent StateGraph
2. 定义节点和边
3. 定义路由函数
"""

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.domain.entities.agent_state import AgentState
from src.infrastructure.agent.nodes.complete_check_node import (
    complete_check_node,
    is_claiming_complete,
)
from src.infrastructure.agent.nodes.context_compact_node import (
    context_compact_node,
)
from src.infrastructure.agent.nodes.llm_call_node import llm_call_node
from src.infrastructure.agent.nodes.loop_detect_node import loop_detect_node
from src.infrastructure.agent.nodes.stuck_detect_node import stuck_detect_node
from src.infrastructure.agent.nodes.tool_execute_node import tool_execute_node


# === Planning-only / Empty 检测关键词 ===

_PLANNING_INDICATORS = [
    "here's a plan",
    "my plan is",
    "i will",
    "let me think",
    "first, i need to",
    "i should",
    "the approach is",
]


def _extract_tool_calls(msg) -> list:
    """从消息中提取 tool_calls 列表"""
    if isinstance(msg, dict):
        return msg.get("tool_calls") or []
    elif hasattr(msg, "tool_calls"):
        return msg.tool_calls or []
    return []


def _extract_text(msg) -> str:
    """从消息中提取文本内容"""
    if isinstance(msg, dict):
        return msg.get("content", "") or ""
    elif hasattr(msg, "content"):
        return msg.content or ""
    return ""


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


def _inject_stuck_feedback(state: AgentState) -> None:
    """注入 Stuck 纠正反馈"""
    stuck_type = state.get("stuck_type", "monologue")
    if stuck_type == "monologue":
        content = (
            "You have been providing analysis without taking action. "
            "Please use an appropriate tool to make progress on the task. "
            "If you need more information, use the available tools first."
        )
    else:
        content = (
            "You appear to be stuck. Please try a different approach to make progress on the task."
        )

    state["messages"].append({"role": "user", "content": content})


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
    """LLM 调用后的路由决策

    判定优先级（从高到低）：
    1. maxTurns 检查
    2. 有 tool_calls -> loop_detect
    3. 声明完成 -> complete_check
    4. Empty Response -> 纠正重试
    5. Planning-only -> 纠正重试
    6. 问用户问题 -> END
    7. 纯文本 -> stuck_detect
    """
    # 0. maxTurns 硬限制
    current_turn = state.get("current_turn", 0)
    max_turns = state.get("max_turns", 100)
    if current_turn >= max_turns:
        state["error"] = f"Max turns ({max_turns}) reached"
        state["should_end"] = True
        return END

    messages = state.get("messages", [])
    if not messages:
        return END

    last_msg = messages[-1]
    tool_calls = _extract_tool_calls(last_msg)
    text = _extract_text(last_msg)

    # 1. 有工具调用 -> loop_detect
    #    pending_tool_calls 已由 llm_call_node 在返回值中设置
    if tool_calls:
        return "loop_detect"

    # 2. 声明完成 -> complete_check
    if is_claiming_complete(text):
        return "complete_check"

    # 3. Empty Response 检测
    if not text.strip():
        state["messages"].append(
            {
                "role": "user",
                "content": (
                    "Your previous response was empty. Please continue working on the task. "
                    "If you're unsure about the next step, read relevant files first."
                ),
            }
        )
        return "llm_call"

    # 4. Planning-only 检测
    text_lower = text.lower()
    is_planning = any(ind in text_lower for ind in _PLANNING_INDICATORS)
    if is_planning:
        state["messages"].append(
            {
                "role": "user",
                "content": (
                    "You outlined a plan but haven't taken action yet. "
                    "Please proceed with executing the plan using the available tools."
                ),
            }
        )
        return "llm_call"

    # 5. 问用户问题 -> END
    if text.strip().endswith("?") or text.strip().endswith("？"):
        state["final_result"] = text
        return END

    # 6. 实质性文本响应（对话场景的正常回答）-> END
    # 纯文本且非空、非计划性，视为最终答案
    state["final_result"] = text
    return END


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


def route_after_stuck_detect(state: AgentState) -> str:
    """Stuck 检测后的路由"""
    if not state.get("stuck_detected"):
        # 未卡住，纯文本响应视为正常，回到 llm_call 继续
        return "llm_call"

    count = state.get("stuck_detection_count", 0)
    if count >= 3:
        # 不可恢复
        stuck_type = state.get("stuck_type", "unknown")
        state["error"] = f"Stuck detected ({stuck_type}), unrecoverable"
        state["should_end"] = True
        return END

    # 注入纠正反馈
    _inject_stuck_feedback(state)
    return "llm_call"


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
                "loop_detect": "loop_detect",
                "stuck_detect": "stuck_detect",
                "complete_check": "complete_check",
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

        # Stuck 检测后条件路由
        workflow.add_conditional_edges(
            "stuck_detect",
            route_after_stuck_detect,
            {
                "llm_call": "llm_call",
                "context_compact": "context_compact",
                END: END,
            },
        )

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
