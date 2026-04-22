"""领域层 - AgentState (LangGraph State)"""

from typing import Annotated, Any, Dict, List, Optional

from typing_extensions import TypedDict
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """Agent 运行状态 — 在节点间传递的共享数据

    这是纯数据结构定义，无框架依赖，符合 DDD 领域层规范。
    LangGraph 的 StateGraph 使用此 TypedDict 作为状态传递。
    """

    # === 消息历史 (LangGraph 自动合并) ===
    messages: Annotated[list, add_messages]

    # === 任务上下文 ===
    task_id: str
    workspace: str
    user_message: str

    # === 控制流 ===
    current_turn: int
    max_turns: int
    phase: str

    # === 工具调用 ===
    pending_tool_calls: List[Dict[str, Any]]
    tool_results: Dict[str, str]

    # === 检测器状态 ===
    loop_detection_count: int
    stuck_detection_count: int

    # === 流式输出 ===
    current_llm_text: str

    # === 结果 ===
    final_result: Optional[str]
    error: Optional[str]
    should_end: bool
