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


class AgentNotFoundError(DomainError):
    """Agent 未找到"""

    pass


class DuplicateAgentNameError(DomainError):
    """Agent 名称重复"""

    pass


# === Tool 相关异常 ===


class ToolError(DomainError):
    """工具系统基础异常"""

    pass


class ToolNotFoundError(ToolError):
    """工具未找到"""

    pass


class ToolExecutionError(ToolError):
    """工具执行失败"""

    pass


class ToolTimeoutError(ToolError):
    """工具执行超时"""

    pass


class ToolRateLimitError(ToolError):
    """工具调用限流"""

    pass
