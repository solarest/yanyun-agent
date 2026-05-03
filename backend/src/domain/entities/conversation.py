"""领域层 - 对话消息和消息组实体"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Literal
import json


@dataclass
class ToolCall:
    """工具调用记录"""
    id: str
    name: str
    arguments: dict
    """调用参数"""

    result: Optional[str] = None
    """调用结果"""

    status: str = "pending"
    """状态：pending / success / error"""

    error: Optional[str] = None
    """错误信息（如有）"""


@dataclass
class ConversationMessage:
    """对话消息领域实体

    表示对话历史中的一条消息，支持多种角色类型。
    通过 to_api_message() 转换为 LLM API 兼容的消息格式。
    """

    role: Literal["system", "user", "assistant", "tool"]
    """消息角色"""

    content: str
    """消息内容"""

    tool_calls: list[ToolCall] = field(default_factory=list)
    """工具调用列表（仅 assistant 角色使用）"""

    tool_call_id: Optional[str] = None
    """关联的工具调用 ID（仅 tool 角色使用）"""

    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_api_message(self) -> dict:
        """转换为 LLM API 兼容的消息格式

        生成符合 OpenAI / LangChain 消息协议的 dict，可直接用于 LLM API 调用。

        Returns:
            LLM API 兼容的消息字典
        """
        if self.role == "user":
            return {"role": "user", "content": self.content}

        elif self.role == "assistant":
            msg: dict = {"role": "assistant", "content": self.content}
            if self.tool_calls:
                msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False)
                        }
                    }
                    for tc in self.tool_calls
                ]
            return msg

        elif self.role == "tool":
            return {
                "role": "tool",
                "tool_call_id": self.tool_call_id,
                "content": self.content
            }

        else:  # system
            return {"role": "system", "content": self.content}

    def estimate_tokens(self) -> int:
        """预估消息的 Token 数量"""
        from .prompt_template import _count_tokens
        text = self.content
        if self.tool_calls:
            text += json.dumps(
                [{"name": tc.name, "arguments": tc.arguments}
                    for tc in self.tool_calls],
                ensure_ascii=False
            )
        return _count_tokens(text)


@dataclass
class MessageGroup:
    """消息组 — 上下文裁剪时的原子单位

    将对话历史中的消息分组为逻辑单元，裁剪时以组为单位操作，
    确保不会拆散一个完整的工具调用轮次。

    分组类型：
    - dialogue: 一轮普通对话 [user, assistant]
    - tool_call_round: 一个完整的工具调用轮次
      [assistant(tool_calls), tool(result) × N]
    """

    type: Literal["dialogue", "tool_call_round"]
    """消息组类型"""

    messages: list[ConversationMessage] = field(default_factory=list)
    """组内的消息列表"""

    token_count: int = 0
    """组内所有消息的 Token 总数"""

    def compute_token_count(self) -> int:
        """计算组内 Token 总数"""
        self.token_count = sum(m.estimate_tokens() for m in self.messages)
        return self.token_count
