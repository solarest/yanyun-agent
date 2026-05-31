"""基础设施层 - LLM 超时错误处理器"""

import asyncio
import logging

from langchain_core.messages import AIMessage

from src.domain.interfaces.llm_error_handler import ILLMErrorHandler

logger = logging.getLogger(__name__)


class TimeoutErrorHandler(ILLMErrorHandler):
    """LLM 调用超时处理"""

    def __init__(self, timeout_sec: int = 300):
        self.timeout_sec = timeout_sec

    def can_handle(self, error: BaseException) -> bool:
        return isinstance(error, TimeoutError) or isinstance(error, asyncio.TimeoutError)

    def handle(self, error: BaseException, state: dict, context) -> dict:
        logger.error(
            "[NODE:llm_call] LLM_CALL_ERROR | agent_id=%s | task_id=%s | turn=%d | "
            "error=timeout | timeout_sec=%d",
            context.agent_id, context.task_id, context.current_turn, self.timeout_sec,
        )
        full_text = state.get("current_llm_text", "")
        thinking_text = state.get("thinking_text", "")
        return {
            "messages": [AIMessage(content=full_text or "LLM call timed out.")],
            "pending_tool_calls": [],
            "current_llm_text": full_text,
            "thinking_text": thinking_text,
            "phase": "thinking",
            "current_turn": context.current_turn + 1,
            "error": f"LLM streaming timed out after {self.timeout_sec}s",
            "should_end": True,
        }
