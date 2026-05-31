"""基础设施层 - 上下文超限错误处理器

LLM 抛出 context window exceeded 错误时：
- 第一次（context_compaction_attempts == 0）：设置 emergency_compact_requested=True, should_end=False
- 第二次（context_compaction_attempts >= 1）：设置 should_end=True, 终止任务
"""

import logging

from src.domain.interfaces.llm_error_handler import ILLMErrorHandler
from src.domain.services.token_utils import is_context_limit_error

logger = logging.getLogger(__name__)


class ContextLimitErrorHandler(ILLMErrorHandler):
    """上下文超限错误处理"""

    def can_handle(self, error: BaseException) -> bool:
        return is_context_limit_error(error)

    def handle(self, error: BaseException, state: dict, context) -> dict:
        attempts = state.get("context_compaction_attempts", 0)

        if attempts == 0:
            logger.warning(
                "[NODE:llm_call] CONTEXT_OVERFLOW | task_id=%s | turn=%d | "
                "error=%s | action=emergency_compact",
                context.task_id, context.current_turn, str(error)[:200],
            )
            return {
                "emergency_compact_requested": True,
                "should_end": False,
                "compression_strategy": "emergency_compact",
                "context_compaction_attempts": 1,
                "error": str(error),
                "phase": "context_overflow",
            }

        logger.error(
            "[NODE:llm_call] CONTEXT_OVERFLOW_FATAL | task_id=%s | turn=%d | "
            "error=%s | attempts=%d",
            context.task_id, context.current_turn, str(error)[:200], attempts,
        )
        return {
            "should_end": True,
            "is_complete": False,
            "error": f"Context window exceeded after emergency compaction: {error}",
            "phase": "error",
        }
