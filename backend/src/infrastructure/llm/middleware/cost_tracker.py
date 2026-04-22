"""基础设施层 - 成本计算器"""

import logging

logger = logging.getLogger(__name__)

# 全局定价表
MODEL_PRICING = {
    # OpenAI
    "gpt-4": (0.03, 0.06),
    "gpt-4-turbo": (0.01, 0.03),
    "gpt-3.5-turbo": (0.0005, 0.0015),
    "gpt-4o": (0.005, 0.015),
    "gpt-4o-mini": (0.00015, 0.0006),
    # Anthropic
    "claude-3-opus": (0.015, 0.075),
    "claude-3-sonnet": (0.003, 0.015),
    "claude-3-haiku": (0.00025, 0.00125),
    "claude-3-5-sonnet": (0.003, 0.015),
}


def calculate_cost(prompt_tokens: int, completion_tokens: int, model: str) -> float:
    """计算 LLM 调用成本

    Args:
        prompt_tokens: 输入 token 数
        completion_tokens: 输出 token 数
        model: 模型名称

    Returns:
        成本（美元）
    """
    pricing = MODEL_PRICING.get(model)

    if pricing is None:
        # 尝试前缀匹配
        for key, price in MODEL_PRICING.items():
            if model.startswith(key):
                pricing = price
                break

    if pricing is None:
        logger.warning(f"未知模型 {model} 的定价，成本计为 0")
        return 0.0

    prompt_price, completion_price = pricing
    return (prompt_tokens / 1000 * prompt_price) + (completion_tokens / 1000 * completion_price)
