"""CostTracker 值对象 — 追踪 LLM 调用的 token 消耗和成本。"""

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass(frozen=True)
class CostTracker:
    """成本追踪器（不可变值对象）"""

    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_cost: float = 0.0

    def add_tokens(self, prompt_tokens: int, completion_tokens: int, pricing: tuple[float, float] | None) -> "CostTracker":
        """返回新的 CostTracker 实例，累加 Token 并计算成本。"""
        new_prompt = self.prompt_tokens + prompt_tokens
        new_completion = self.completion_tokens + completion_tokens
        new_cost = self.total_cost

        if pricing:
            prompt_price, completion_price = pricing
            new_cost += (prompt_tokens / 1000 * prompt_price) + (completion_tokens / 1000 * completion_price)

        return CostTracker(
            prompt_tokens=new_prompt,
            completion_tokens=new_completion,
            total_tokens=new_prompt + new_completion,
            total_cost=new_cost,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_tokens": self.total_tokens,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_cost": self.total_cost,
        }
