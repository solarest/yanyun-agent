"""基础设施层 - LLM 调用节点

LangGraph Node: llm_call_node
职责：调用 LLM 并流式输出文本到前端
"""
from langchain_core.messages import AIMessage
from langgraph.types import RunnableConfig

from src.domain.entities.agent_state import AgentState


async def llm_call_node(state: AgentState, config: RunnableConfig) -> dict:
    """LLM 调用节点
    
    1. 发射阶段变更事件
    2. 流式调用 LLM
    3. 发射每个 token (llm-chunk)
    4. 返回累积文本
    
    Args:
        state: 当前 Agent 状态
        config: LangGraph 配置 (包含 llm, event_service 等)
        
    Returns:
        状态更新字典
    """
    llm = config["configurable"]["llm"]
    event_svc = config["configurable"]["event_service"]
    task_id = state["task_id"]
    current_turn = state["current_turn"]
    
    # 发射阶段变更事件
    await event_svc.emit(task_id, "phase-changed", {
        "phase": "thinking",
        "previousPhase": state.get("phase", "idle"),
        "turn": current_turn,
    })
    
    # 流式调用 LLM
    messages = state["messages"]
    full_text = ""
    tool_calls_list = []
    
    async for chunk in llm.astream(messages):
        if chunk.content:
            full_text += chunk.content
            # 发射流式片段
            await event_svc.emit(task_id, "llm-chunk", {
                "turn": current_turn,
                "text": chunk.content,
                "delta": True,
            })
        
        # 收集工具调用
        if hasattr(chunk, "tool_calls") and chunk.tool_calls:
            tool_calls_list.extend(chunk.tool_calls)
    
    # 发射 LLM 完成事件
    await event_svc.emit(task_id, "llm-complete", {
        "turn": current_turn,
        "fullText": full_text,
        "toolCalls": tool_calls_list,
    })
    
    # 返回状态更新
    return {
        "messages": [AIMessage(content=full_text, tool_calls=tool_calls_list if tool_calls_list else None)],
        "current_llm_text": full_text,
        "phase": "thinking",
    }
