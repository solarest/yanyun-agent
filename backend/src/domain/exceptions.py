"""领域层 - 异常定义"""


class DomainError(Exception):
    """领域层基础异常"""

    pass


class EntityNotFoundError(DomainError):
    """实体未找到"""

    pass


class ValidationError(DomainError):
    """验证错误"""

    pass


class LLMError(DomainError):
    """LLM 调用基础异常"""

    pass


class LLMTimeoutError(LLMError):
    """LLM 调用超时"""

    pass


class LLMRateLimitError(LLMError):
    """LLM 速率限制"""

    pass


class LLMProviderNotSupportedError(LLMError):
    """不支持的 LLM 提供商"""

    pass
