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
    task_start_message_count: int

    # === 控制流 ===
    current_turn: int
    max_turns: int
    phase: str
    should_end: bool
    is_complete: bool

    # === 工具调用 ===
    pending_tool_calls: List[Dict[str, Any]]
    tool_results: Dict[str, Dict[str, Any]]
    awaiting_user_input: bool
    last_executed_tool_call_ids: List[str]

    # === Loop 检测器状态 ===
    loop_detection_count: int
    loop_detected: bool
    loop_type: Optional[str]

    # === Stuck 检测器状态 ===
    stuck_detection_count: int
    stuck_detected: bool
    stuck_type: Optional[str]

    # === 流式输出 ===
    current_llm_text: str
    empty_retry_count: int
    planning_retry_count: int

    # === 系统提示词 ===
    system_prompt: str

    # === 结果 ===
    final_result: Optional[str]
    error: Optional[str]

    # === Observation 状态（observe_node 写入）===
    observation_summary: Optional[str]
    """本轮观察文本总结（供调试/前端展示）"""

    observation_quality: Optional[str]
    """本轮观察总体质量：good / empty / partial / failed / mixed"""

    observation_items: List[Dict[str, Any]]
    """每个 tool_call 的观察详情"""

    consecutive_empty_observations: int
    """连续空观察计数（触发语义循环检测）"""

    last_error_category: Optional[str]
    """最近一次错误分类"""

    route_hint: Optional[str]
    """observe_node 给出的路由建议（llm_call / loop_detect / finalize）"""

    # === Plan 执行状态 ===
    plan: Optional[Dict[str, Any]]
    """当前plan结构"""
    
    plan_results: Dict[int, Dict[str, Any]]
    """各步骤执行结果 {step_id: result}"""
    
    is_sub_agent: bool
    """是否为子Agent"""
    
    parent_task_id: Optional[str]
    """父Agent的task_id(子Agent用)"""
