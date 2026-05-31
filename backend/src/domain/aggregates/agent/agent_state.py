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
    model: str
    """LLM 模型名称（如 gpt-4, qwen-plus 等）"""

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

    # === 流式输出 ===
    current_llm_text: str
    empty_retry_count: int

    # === 系统提示词 ===
    system_prompt: str

    # === 深度思考 ===
    thinking_text: str
    """LLM 深度思考/推理内容（如 DeepSeek reasoning_content）"""

    # === 结果 ===
    final_result: Optional[str]
    error: Optional[str]

    # === 压缩策略 ===
    compression_strategy: Optional[str]
    """context_compact 使用的压缩策略：trim / summarize"""

    # === 上下文管理 ===
    max_context_tokens: int
    """当前模型上下文窗口 Token 数上限"""
    context_token_estimate: int
    """当前 messages 的 Token 估算值"""
    context_token_baseline: Optional[int]
    """最近一次成功 LLM 调用返回的 prompt_tokens"""
    context_token_baseline_message_count: int
    """baseline 对应的消息数量，用于增量估算"""
    context_compaction_attempts: int
    """连续紧急压缩次数"""
    emergency_compact_requested: bool
    """LLM 调用发生上下文超限后置为 True"""
    last_context_strategy: Optional[str]
    """最近一次实际执行的压缩策略"""

    # === Sub-Agent 状态 ===
    is_sub_agent: bool
    """是否为子Agent"""

    parent_task_id: Optional[str]
    """父Agent的task_id(子Agent用)"""
