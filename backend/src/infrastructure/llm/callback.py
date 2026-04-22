"""基础设施层 - LangChain CallbackHandler"""
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from src.domain.entities.task import CostTracker
from src.infrastructure.llm.middleware.cost_tracker import calculate_cost


class LLMUsageCallbackHandler(BaseCallbackHandler):
    """LangChain CallbackHandler - 自动收集 Token 和成本数据
    
    通过 LangChain 的回调机制，在每次 LLM 调用时自动收集
    Token 使用量和成本数据。
    
    Attributes:
        model_name: 模型名称
        total_prompt_tokens: 总输入 token 数
        total_completion_tokens: 总输出 token 数
        total_cost: 总成本（美元）
    """
    
    def __init__(self, model_name: str):
        self.model_name = model_name
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_cost = 0.0
    
    def on_llm_end(self, response: LLMResult, **kwargs) -> None:
        """LLM 调用结束时提取 usage 信息"""
        if response.llm_output and "token_usage" in response.llm_output:
            usage = response.llm_output["token_usage"]
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            
            self.total_prompt_tokens += prompt_tokens
            self.total_completion_tokens += completion_tokens
            
            cost = calculate_cost(prompt_tokens, completion_tokens, self.model_name)
            self.total_cost += cost
    
    def get_cost_tracker(self) -> CostTracker:
        """返回 CostTracker 实体"""
        return CostTracker(
            total_tokens=self.total_prompt_tokens + self.total_completion_tokens,
            prompt_tokens=self.total_prompt_tokens,
            completion_tokens=self.total_completion_tokens,
            total_cost=self.total_cost,
        )
