"""基础设施层 - Loop 检测节点

LangGraph Node: loop_detect_node
职责：检测 Agent 是否进入循环模式
"""
from collections import Counter
from langgraph.types import RunnableConfig

from src.domain.entities.agent_state import AgentState


async def loop_detect_node(state: AgentState, config: RunnableConfig) -> dict:
    """Loop 检测节点
    
    检测策略：
    1. 精确匹配：最近 N 轮是否调用相同工具 + 相同参数
    2. 内容相似度：LLM 响应文本相似度
    
    Args:
        state: 当前 Agent 状态
        config: LangGraph 配置
        
    Returns:
        状态更新字典 (包含 loop_detected 标志)
    """
    messages = state["messages"]
    threshold = 3  # 连续重复阈值
    window = 5     # 检测窗口
    
    # 提取最近的工具调用
    recent_tool_calls = []
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get("role") == "assistant" and msg.get("tool_calls"):
            recent_tool_calls.append(msg["tool_calls"])
            if len(recent_tool_calls) >= window:
                break
    
    # 精确匹配检测
    loop_detected = False
    loop_type = None
    
    if len(recent_tool_calls) >= threshold:
        # 检查最近 N 轮工具调用是否相同
        signatures = []
        for tc_list in recent_tool_calls[:threshold]:
            if not tc_list:
                break
            # 工具名 + 参数 hash
            sig = tuple(
                (tc.get("name"), hash(frozenset(tc.get("arguments", {}).items())))
                for tc in tc_list
            )
            signatures.append(sig)
        
        if len(signatures) == threshold and len(set(signatures)) == 1:
            loop_detected = True
            loop_type = "exact_tool_repeat"
    
    # 内容相似度检测 (简化版：基于词袋重叠)
    if not loop_detected:
        assistant_texts = []
        for msg in reversed(messages):
            if isinstance(msg, dict) and msg.get("role") == "assistant" and msg.get("content"):
                assistant_texts.append(msg["content"])
                if len(assistant_texts) >= 4:
                    break
        
        if len(assistant_texts) >= 2:
            similarities = []
            for i in range(len(assistant_texts) - 1):
                words1 = Counter(assistant_texts[i].split())
                words2 = Counter(assistant_texts[i + 1].split())
                intersection = sum((words1 & words2).values())
                union = sum((words1 | words2).values())
                sim = intersection / union if union > 0 else 0
                similarities.append(sim)
            
            if similarities and all(s > 0.85 for s in similarities):
                loop_detected = True
                loop_type = "content_repeat"
    
    if loop_detected:
        return {
            "loop_detected": True,
            "loop_detection_count": state.get("loop_detection_count", 0) + 1,
            "loop_type": loop_type,
        }
    
    return {"loop_detected": False}
