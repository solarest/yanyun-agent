"""领域服务 - 消息内容提取工具

从消息和工具结果中提取文本内容的纯领域工具函数。
"""

from typing import Any, Dict


class MessageContentService:
    """消息内容提取工具服务。

    提供从消息列表、工具结果等数据结构中提取文本内容的纯函数。
    """

    @staticmethod
    def extract_tool_output(tool_result: Dict[str, Any]) -> str:
        """统一提取工具结果的文本：优先 output，其次 error，都没有返回空串。"""
        return tool_result.get("output") or tool_result.get("error") or ""

    @staticmethod
    def extract_last_content(messages: list) -> str:
        """从消息列表倒序查找第一条非空 content，找不到返回空串。

        兼容 dict 和 LangChain Message 对象两种形式。
        """
        for msg in reversed(messages):
            if isinstance(msg, dict):
                content = msg.get("content", "")
            else:
                content = getattr(msg, "content", "") or ""
            if content:
                return content
        return ""
