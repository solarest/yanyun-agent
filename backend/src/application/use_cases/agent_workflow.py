"""应用层 - Agent 工作流用例

职责：
1. 构建 Agent StateGraph
2. 定义节点和边
3. 定义路由函数（纯判定，不修改 state）
4. 定义反馈注入节点（通过返回 dict 更新 state）
"""

from langchain_core.messages import HumanMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import RunnableConfig

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


# === 检测关键词（中英文） ===

_PLANNING_INDICATORS = [
    # English
    "here's a plan",
    "my plan is",
    "i will",
    "let me think",
    "first, i need to",
    "i should",
    "the approach is",
    # Chinese
    "我的计划是",
    "让我想想",
    "我需要先",
    "我应该",
    "方案是",
    "思路是",
    "计划如下",
    "步骤如下",
]

_EMPTY_MAX_RETRY = 2
_PLANNING_MAX_RETRY = 2


# === 辅助函数 ===


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


def _exhausted_turn_budget(state: AgentState) -> bool:
    """当前响应已消耗最后一个 LLM turn，无法再继续下一轮。"""
    return state.get("current_turn", 0) >= state.get("max_turns", 100)


def _is_planning_only(text_lower: str) -> bool:
    """检测文本是否仅为纯规划/思考内容"""
    return any(ind in text_lower for ind in _PLANNING_INDICATORS)


def _is_user_question(text: str) -> bool:
    """检测 LLM 是否在向用户提问并等待输入。

    仅检查最后一行是否以问号结尾，避免中间反问句误判终止。
    """
    stripped = text.strip()
    if not stripped:
        return False
    last_line = stripped.rsplit("\n", 1)[-1].strip()
    return last_line.endswith("?") or last_line.endswith("？")


# === 反馈注入节点 ===
# 每个节点通过返回 dict 正确更新 state，不直接 mutate。


async def empty_feedback_node(state: AgentState, config: RunnableConfig) -> dict:
    """空响应纠正节点：注入提示消息或终止"""
    count = state.get("empty_retry_count", 0) + 1
    if count > _EMPTY_MAX_RETRY:
        return {
            "empty_retry_count": count,
            "error": "Empty response persists after correction",
            "should_end": True,
        }
    if _exhausted_turn_budget(state):
        return {
            "empty_retry_count": count,
            "error": f"Max turns ({state.get('max_turns', 100)}) reached after empty response",
            "should_end": True,
        }
    return {
        "messages": [
            HumanMessage(
                content=(
                    "Your previous response was empty. Please continue working on the task. "
                    "If you're unsure about the next step, read relevant files first."
                )
            )
        ],
        "empty_retry_count": count,
    }


async def planning_feedback_node(state: AgentState, config: RunnableConfig) -> dict:
    """纯规划纠正节点：注入行动提示或终止"""
    count = state.get("planning_retry_count", 0) + 1
    if count > _PLANNING_MAX_RETRY:
        return {
            "planning_retry_count": count,
            "error": "Planning-only persists after correction",
            "should_end": True,
        }
    if _exhausted_turn_budget(state):
        return {
            "planning_retry_count": count,
            "error": f"Max turns ({state.get('max_turns', 100)}) reached after planning-only response",
            "should_end": True,
        }
    return {
        "messages": [
            HumanMessage(
                content=(
                    "You outlined a plan but haven't taken action yet. "
                    "Please proceed with executing the plan using the available tools."
                )
            )
        ],
        "planning_retry_count": count,
    }


async def loop_feedback_node(state: AgentState, config: RunnableConfig) -> dict:
    """循环纠正节点：根据连续检测次数升级处理策略"""
    count = state.get("loop_detection_count", 0)
    if count >= 3:
        return {
            "error": "Loop detected, terminating after 3 attempts",
            "should_end": True,
        }
    if count == 2:
        # route_after_loop_feedback 会将其路由到 context_compact
        return {}
    if _exhausted_turn_budget(state):
        return {
            "error": f"Max turns ({state.get('max_turns', 100)}) reached during loop recovery",
            "should_end": True,
        }
    return {
        "messages": [
            HumanMessage(
                content=(
                    "WARNING: You seem to be repeating the same actions. "
                    "Please try a different approach to solve the task. "
                    "Analyze what went wrong and propose a new strategy."
                )
            )
        ],
    }


async def stuck_feedback_node(state: AgentState, config: RunnableConfig) -> dict:
    """卡住纠正节点：注入纠正反馈或终止"""
    count = state.get("stuck_detection_count", 0)
    if count >= 3:
        stuck_type = state.get("stuck_type", "unknown")
        return {
            "error": f"Stuck detected ({stuck_type}), unrecoverable",
            "should_end": True,
        }
    if _exhausted_turn_budget(state):
        return {
            "error": f"Max turns ({state.get('max_turns', 100)}) reached during stuck recovery",
            "should_end": True,
        }
    stuck_type = state.get("stuck_type", "monologue")
    if stuck_type == "monologue":
        content = (
            "You have been providing analysis without taking action. "
            "Please use an appropriate tool to make progress on the task. "
            "If you need more information, use the available tools first."
        )
    else:
        content = (
            "You appear to be stuck. "
            "Please try a different approach to make progress on the task."
        )
    return {"messages": [HumanMessage(content=content)]}


async def completion_feedback_node(
    state: AgentState, config: RunnableConfig
) -> dict:
    """完成纠正节点：任务未真正完成时注入继续工作提示"""
    if _exhausted_turn_budget(state):
        return {
            "error": f"Max turns ({state.get('max_turns', 100)}) reached after incomplete completion check",
            "should_end": True,
        }
    return {
        "messages": [
            HumanMessage(
                content=(
                    "You claimed the task is complete, but it appears there is still work to do. "
                    "Please continue working on the task."
                )
            )
        ],
    }


async def finalize_result_node(state: AgentState, config: RunnableConfig) -> dict:
    """结果终结节点：从最后消息提取 final_result"""
    messages = state.get("messages", [])
    text = _extract_text(messages[-1]) if messages else ""
    return {"final_result": text}


async def terminate_node(state: AgentState, config: RunnableConfig) -> dict:
    """终止节点：设置超限错误"""
    max_turns = state.get("max_turns", 100)
    return {
        "error": f"Max turns ({max_turns}) reached before tool execution follow-up",
        "should_end": True,
    }


# === 路由函数（纯判定，不修改 state） ===


def route_after_llm(state: AgentState) -> str:
    """LLM 调用后的路由决策

    判定优先级（从高到低）：
    1. 有 tool_calls + 超限 -> terminate
    2. 有 tool_calls -> loop_detect
    3. 声明完成 -> complete_check
    4. Empty Response -> empty_feedback
    5. Planning-only -> planning_feedback
    6. 问用户问题 -> finalize_result
    7. 纯文本 -> stuck_detect
    """
    messages = state.get("messages", [])
    if not messages:
        return END

    # 前置检查：如果节点已标记 should_end（如 LLM 超时），直接终止
    if state.get("should_end"):
        return END

    last_msg = messages[-1]
    tool_calls = _extract_tool_calls(last_msg)
    text = _extract_text(last_msg)

    # 1. 有工具调用
    if tool_calls:
        if _exhausted_turn_budget(state):
            return "terminate"
        return "loop_detect"

    # 2. 声明完成
    if is_claiming_complete(text):
        return "complete_check"

    # 3. 空响应
    if not text.strip():
        return "empty_feedback"

    # 4. 纯规划
    text_lower = text.lower()
    if _is_planning_only(text_lower):
        return "planning_feedback"

    # 5. 向用户提问
    if _is_user_question(text):
        return "finalize_result"

    # 6. 实质性文本 → 卡住检测
    return "stuck_detect"


def route_after_loop_detect(state: AgentState) -> str:
    """Loop 检测后：无循环 → 执行工具，有循环 → 反馈节点"""
    if not state.get("loop_detected"):
        return "tool_execute"
    return "loop_feedback"


def route_after_loop_feedback(state: AgentState) -> str:
    """Loop 反馈后：根据 should_end 和检测次数路由"""
    if state.get("should_end"):
        return END
    if state.get("loop_detection_count", 0) == 2:
        return "context_compact"
    return "llm_call"


def route_after_stuck_detect(state: AgentState) -> str:
    """Stuck 检测后：无卡住 → 结果终结，有卡住 → 反馈节点"""
    if not state.get("stuck_detected"):
        return "finalize_result"
    return "stuck_feedback"


def route_after_feedback(state: AgentState) -> str:
    """通用反馈后路由：should_end 则终止，否则回到 LLM"""
    if state.get("should_end"):
        return END
    return "llm_call"


def route_after_complete_check(state: AgentState) -> str:
    """完成检查后：完成 → 结束，未完成 → 完成纠正"""
    if state.get("is_complete"):
        return END
    return "completion_feedback"


def route_after_tool_execute(state: AgentState) -> str:
    """工具执行后的路由。"""
    if state.get("awaiting_user_input"):
        return END
    return "llm_call"


# === 工作流构建器 ===


class AgentWorkflowBuilder:
    """Agent StateGraph 构建器"""

    _compiled: CompiledStateGraph | None = None

    @classmethod
    def build(cls) -> CompiledStateGraph:
        """构建并编译 StateGraph（单例缓存）"""
        if cls._compiled is not None:
            return cls._compiled

        workflow = StateGraph(AgentState)

        # === 核心节点 ===
        workflow.add_node("llm_call", llm_call_node)
        workflow.add_node("tool_execute", tool_execute_node)
        workflow.add_node("loop_detect", loop_detect_node)
        workflow.add_node("stuck_detect", stuck_detect_node)
        workflow.add_node("context_compact", context_compact_node)
        workflow.add_node("complete_check", complete_check_node)

        # === 反馈注入节点 ===
        workflow.add_node("empty_feedback", empty_feedback_node)
        workflow.add_node("planning_feedback", planning_feedback_node)
        workflow.add_node("loop_feedback", loop_feedback_node)
        workflow.add_node("stuck_feedback", stuck_feedback_node)
        workflow.add_node("completion_feedback", completion_feedback_node)
        workflow.add_node("finalize_result", finalize_result_node)
        workflow.add_node("terminate", terminate_node)

        # === 入口 ===
        workflow.set_entry_point("llm_call")

        # === LLM 后路由 ===
        workflow.add_conditional_edges(
            "llm_call",
            route_after_llm,
            {
                "loop_detect": "loop_detect",
                "stuck_detect": "stuck_detect",
                "complete_check": "complete_check",
                "empty_feedback": "empty_feedback",
                "planning_feedback": "planning_feedback",
                "finalize_result": "finalize_result",
                "terminate": "terminate",
                END: END,
            },
        )

        # === 工具执行后路由 ===
        workflow.add_conditional_edges(
            "tool_execute",
            route_after_tool_execute,
            {"llm_call": "llm_call", END: END},
        )

        # === Loop 检测后路由 ===
        workflow.add_conditional_edges(
            "loop_detect",
            route_after_loop_detect,
            {"tool_execute": "tool_execute", "loop_feedback": "loop_feedback"},
        )

        # === Loop 反馈后路由 ===
        workflow.add_conditional_edges(
            "loop_feedback",
            route_after_loop_feedback,
            {"llm_call": "llm_call", "context_compact": "context_compact", END: END},
        )

        # === Stuck 检测后路由 ===
        workflow.add_conditional_edges(
            "stuck_detect",
            route_after_stuck_detect,
            {"finalize_result": "finalize_result", "stuck_feedback": "stuck_feedback"},
        )

        # === 完成检查后路由 ===
        workflow.add_conditional_edges(
            "complete_check",
            route_after_complete_check,
            {"completion_feedback": "completion_feedback", END: END},
        )

        # === 反馈节点统一后续路由 ===
        for node_name in (
            "empty_feedback",
            "planning_feedback",
            "stuck_feedback",
            "completion_feedback",
        ):
            workflow.add_conditional_edges(
                node_name,
                route_after_feedback,
                {"llm_call": "llm_call", END: END},
            )

        # === 固定后续边 ===
        workflow.add_edge("context_compact", "llm_call")
        workflow.add_edge("finalize_result", END)
        workflow.add_edge("terminate", END)

        cls._compiled = workflow.compile()
        return cls._compiled
