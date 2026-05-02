"""基础设施层 - LangChain CallbackHandler"""

import json
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult

from src.domain.entities.task import CostTracker
from src.infrastructure.llm.middleware.cost_tracker import calculate_cost

# 独立的 LLM 调用日志记录器（记录完整入参/出参）
llm_logger = logging.getLogger("llm.call")


def _serialize_messages(messages: List[BaseMessage]) -> list:
    """将 LangChain 消息序列化为可读 dict，保留完整内容与工具调用信息"""
    result = []
    for msg in messages:
        item: dict = {
            "role": getattr(msg, "type", msg.__class__.__name__),
            "content": msg.content,
        }
        tool_calls = getattr(msg, "tool_calls", None)
        if tool_calls:
            item["tool_calls"] = tool_calls
        tool_call_id = getattr(msg, "tool_call_id", None)
        if tool_call_id:
            item["tool_call_id"] = tool_call_id
        name = getattr(msg, "name", None)
        if name:
            item["name"] = name
        result.append(item)
    return result


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


class LLMCallLogger(BaseCallbackHandler):
    """LangChain CallbackHandler - 在 LLM 发起 API 请求的前后记录完整参数

    触发时机贴近真正的 HTTP 请求：
    - on_chat_model_start: LangChain 将参数交给 provider client 之前，
      此时 kwargs['invocation_params'] 包含最终会传入 OpenAI SDK 的全部参数
      （包括 model / temperature / tools / tool_choice / stream / max_tokens 等）
    - on_llm_end: 聚合完成后触发，可拿到 generations / tool_calls / usage

    通过 LangChain 的 config.metadata 机制从调用方携带 agent_id / task_id / turn
    等上下文，避免回调无法关联业务语义。
    """

    def on_chat_model_start(
        self,
        serialized: Dict[str, Any],
        messages: List[List[BaseMessage]],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> None:
        meta = metadata or {}
        invocation_params: Dict[str, Any] = kwargs.get("invocation_params") or {}
        serialized_kwargs: Dict[str, Any] = (
            serialized.get("kwargs", {}) if isinstance(serialized, dict) else {}
        )

        payload = {
            "run_id": str(run_id),
            "agent_id": meta.get("agent_id", "unknown"),
            "task_id": meta.get("task_id", "unknown"),
            "turn": meta.get("turn"),
            "model": (
                invocation_params.get("model")
                or invocation_params.get("model_name")
                or serialized_kwargs.get("model_name")
                or serialized_kwargs.get("model")
            ),
            "temperature": invocation_params.get("temperature"),
            "max_tokens": invocation_params.get("max_tokens"),
            "stream": invocation_params.get("stream"),
            "tools": invocation_params.get("tools") or serialized_kwargs.get("tools"),
            "tool_choice": invocation_params.get("tool_choice"),
            "invocation_params": invocation_params,
            "messages": [_serialize_messages(msgs) for msgs in messages],
        }
        llm_logger.info(
            "[LLM-REQUEST] %s",
            json.dumps(payload, ensure_ascii=False, default=str),
        )

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        generations = []
        for gens in response.generations:
            for gen in gens:
                item: dict = {"text": gen.text}
                msg = getattr(gen, "message", None)
                if msg is not None:
                    item["content"] = getattr(msg, "content", None)
                    item["tool_calls"] = getattr(msg, "tool_calls", None)
                    item["response_metadata"] = getattr(msg, "response_metadata", None)
                    item["usage_metadata"] = getattr(msg, "usage_metadata", None)
                generations.append(item)

        payload = {
            "run_id": str(run_id),
            "llm_output": response.llm_output,
            "generations": generations,
        }
        llm_logger.info(
            "[LLM-RESPONSE] %s",
            json.dumps(payload, ensure_ascii=False, default=str),
        )

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        llm_logger.error(
            "[LLM-ERROR] run_id=%s error=%s",
            str(run_id),
            repr(error),
        )
