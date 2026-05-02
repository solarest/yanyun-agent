"""基础设施层 - 完成检查节点

LangGraph Node: complete_check_node
职责：使用 LLM + 规则混合判断任务是否完成

设计原则：
1. 规则作为快速路径（高置信度情况直接判断）
2. LLM 作为智能判断（复杂情况交给 LLM 分析）
3. 降级保护（LLM 调用失败时回退到规则）
"""
import logging
from typing import Any, Dict, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.types import RunnableConfig

from src.domain.entities.agent_state import AgentState

logger = logging.getLogger(__name__)


# === 规则判断：高置信度快速路径 ===

# 明确的完成声明关键词（中英文）
STRONG_COMPLETION_PHRASES = [
    # English
    "task complete",
    "i have completed the task",
    "i've completed the task",
    "the task is done",
    "everything is done",
    "all done",
    # Chinese
    "任务完成",
    "任务已完成",
    "全部完成",
    "所有步骤已完成",
    "工作已完成",
]

# 明确的未完成信号
STRONG_INCOMPLETE_PHRASES = [
    # English
    "i need to",
    "i should",
    "let me continue",
    "next, i will",
    "moving on to",
    # Chinese
    "我需要",
    "我应该",
    "让我继续",
    "接下来我将",
    "下一步",
]


def rule_based_completion_check(text: str) -> Optional[bool]:
    """基于规则的快速判断
    
    Returns:
        True - 明确完成
        False - 明确未完成
        None - 不确定，需要 LLM 判断
    """
    text_lower = text.lower()
    
    # 检查明确的完成信号
    has_completion = any(phrase in text_lower for phrase in STRONG_COMPLETION_PHRASES)
    
    # 检查明确的未完成信号
    has_incomplete = any(phrase in text_lower for phrase in STRONG_INCOMPLETE_PHRASES)
    
    # 如果同时出现，说明还在继续工作，未完成
    if has_completion and has_incomplete:
        return False
    
    # 如果有明确的完成信号
    if has_completion:
        return True
    
    # 如果有明确的未完成信号
    if has_incomplete:
        return False
    
    # 否则不确定，需要 LLM 判断
    return None


# === LLM 判断：智能分析路径 ===

COMPLETION_CHECK_SYSTEM_PROMPT = """You are an expert at evaluating whether an AI agent has completed its task.

Analyze the agent's response and determine if it has truly completed the task.

Evaluation criteria:
1. **Completion**: The agent explicitly states or implies the task is done
2. **Substance**: The response contains actual results, not just planning
3. **Finality**: The agent is not indicating it needs to continue working

Consider these as COMPLETION signals:
- "I have completed..."
- "Here are the results..."
- "The task is done..."
- Summary of work done with concrete outcomes
- Asking user if they need anything else

Consider these as INCOMPLETE signals:
- "I will..." / "I should..." (future actions)
- "Let me continue..."
- Planning next steps without executing
- Only analysis without action

Respond with a JSON object:
{
  "is_complete": true/false,
  "confidence": 0.0-1.0,
  "reason": "brief explanation"
}"""

COMPLETION_CHECK_USER_PROMPT = """Task context: {task_description}

Agent's response:
{text}

Evaluate whether the agent has completed the task."""


async def llm_based_completion_check(
    text: str,
    task_description: Optional[str],
    llm: Any,
) -> Dict[str, Any]:
    """使用 LLM 智能判断任务是否完成
    
    Returns:
        {
            "is_complete": bool,
            "confidence": float,
            "reason": str
        }
    """
    try:
        system_msg = SystemMessage(content=COMPLETION_CHECK_SYSTEM_PROMPT)
        user_content = COMPLETION_CHECK_USER_PROMPT.format(
            task_description=task_description or "No specific task description provided.",
            text=text[:2000],  # 限制长度避免 token 过多
        )
        user_msg = HumanMessage(content=user_content)
        
        # 调用 LLM
        response = await llm.ainvoke([system_msg, user_msg])
        
        # 解析响应
        response_text = response.content if hasattr(response, 'content') else str(response)
        
        # 尝试提取 JSON
        import json
        import re
        
        # 查找 JSON 块
        json_match = re.search(r'\{[^}]*\}', response_text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            return {
                "is_complete": result.get("is_complete", False),
                "confidence": result.get("confidence", 0.5),
                "reason": result.get("reason", "LLM evaluation"),
            }
        
        # 如果没有 JSON，尝试从文本判断
        response_lower = response_text.lower()
        is_complete = any(word in response_lower for word in ["true", "yes", "completed", "done"])
        
        return {
            "is_complete": is_complete,
            "confidence": 0.5,
            "reason": "Fallback text analysis",
        }
        
    except Exception as e:
        logger.warning("LLM completion check failed: %s", e)
        return {
            "is_complete": False,
            "confidence": 0.0,
            "reason": f"LLM evaluation failed: {str(e)}",
        }


# === 主节点 ===


def _extract_text_from_message(msg) -> str:
    """从消息中提取文本"""
    if isinstance(msg, dict):
        return msg.get("content", "") or ""
    elif hasattr(msg, "content"):
        return msg.content or ""
    return ""


async def complete_check_node(state: AgentState, config: RunnableConfig) -> dict:
    """完成检查节点 - 混合 LLM + 规则判断
    
    判断流程：
    1. 规则快速判断（高置信度）
    2. LLM 智能判断（复杂情况）
    3. 降级保护（LLM 失败时）
    
    Args:
        state: 当前 Agent 状态
        config: LangGraph 配置
    
    Returns:
        状态更新字典
    """
    messages = state.get("messages", [])
    if not messages:
        return {"is_complete": False, "completion_check_method": "rule", "completion_conffidence": 0.0}
    
    last_msg = messages[-1]
    text = _extract_text_from_message(last_msg)
    
    if not text.strip():
        return {"is_complete": False, "completion_check_method": "rule", "completion_confidence": 0.0}
    
    # === Step 1: 规则快速判断 ===
    rule_result = rule_based_completion_check(text)
    
    if rule_result is not None:
        # 规则有明确判断
        logger.info(
            "Completion check by rules: %s (text_length=%d)",
            "complete" if rule_result else "incomplete",
            len(text),
        )
        
        if rule_result:
            return {
                "is_complete": True,
                "final_result": text,
                "phase": "complete",
                "completion_check_method": "rule",
                "completion_confidence": 1.0,
                "completion_reason": "Strong completion signals detected",
            }
        else:
            return {
                "is_complete": False,
                "completion_check_method": "rule",
                "completion_confidence": 1.0,
                "completion_reason": "Strong incomplete signals detected",
            }
    
    # === Step 2: LLM 智能判断 ===
    logger.info("Rule-based check inconclusive, using LLM for completion check")
    
    llm = config.get("configurable", {}).get("llm")
    if not llm:
        logger.warning("LLM not available, falling back to incomplete")
        return {
            "is_complete": False,
            "completion_check_method": "fallback",
            "completion_confidence": 0.0,
            "completion_reason": "LLM not available",
        }
    
    task_description = state.get("system_prompt", "") or state.get("task_description", "")
    
    llm_result = await llm_based_completion_check(text, task_description, llm)
    
    logger.info(
        "LLM completion check: %s (confidence=%.2f, reason=%s)",
        "complete" if llm_result["is_complete"] else "incomplete",
        llm_result["confidence"],
        llm_result["reason"],
    )
    
    if llm_result["is_complete"] and llm_result["confidence"] >= 0.7:
        return {
            "is_complete": True,
            "final_result": text,
            "phase": "complete",
            "completion_check_method": "llm",
            "completion_confidence": llm_result["confidence"],
            "completion_reason": llm_result["reason"],
        }
    else:
        return {
            "is_complete": False,
            "completion_check_method": "llm",
            "completion_confidence": llm_result["confidence"],
            "completion_reason": llm_result["reason"],
        }
