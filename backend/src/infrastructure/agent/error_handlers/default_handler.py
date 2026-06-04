"""基础设施层 - 默认 LLM 错误处理器

不处理任何错误，re-raise 让 BaseNode._handle_error 统一处理。
"""

import logging

from src.domain.interfaces.llm_error_handler import ILLMErrorHandler

logger = logging.getLogger(__name__)


class DefaultErrorHandler(ILLMErrorHandler):
    """默认错误处理器 — re-raise 给 BaseNode"""

    def can_handle(self, error: BaseException) -> bool:
        # 作为兜底 handler，始终返回 True
        return True

    def handle(self, error: BaseException, state: dict, context) -> dict:
        # re-raise 让 BaseNode._handle_error 处理
        raise error
