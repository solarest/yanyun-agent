"""基础设施层 - LLM 重试机制"""

from typing import Callable

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    retry_if_not_exception_type,
)


def create_retry_decorator(
    max_attempts: int = 3,
    min_wait: float = 1.0,
    max_wait: float = 30.0,
) -> Callable:
    """创建重试装饰器

    使用指数退避策略进行重试。

    Args:
        max_attempts: 最大重试次数
        min_wait: 最小等待时间（秒）
        max_wait: 最大等待时间（秒）

    Returns:
        tenacity 重试装饰器
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
        retry=retry_if_exception_type((Exception,))
        & retry_if_not_exception_type(
            (
                KeyboardInterrupt,
                SystemExit,
            )
        ),
        reraise=True,
    )
