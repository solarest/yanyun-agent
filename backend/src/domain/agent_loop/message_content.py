"""领域服务 - 消息内容提取工具

从消息和工具结果中提取文本内容的纯领域工具函数。
"""

from typing import Any, Dict, List


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

    @staticmethod
    def extract_all_llm_content(messages: list) -> str:
        """拼接消息列表中所有 AI/LLM 消息的 content 文本。

        当 Agent 在多轮 ReAct 中产生多次 LLM 调用时，
        仅取最后一条消息会丢失前面的分析正文。
        本方法收集所有 AI 消息的 content，用双换行拼接。

        仅收集 AI 消息 (AIMessage / role=assistant / 含 tool_calls)，
        跳过 HumanMessage / SystemMessage / ToolMessage。
        """
        collected: List[str] = []

        def _is_tool_message(msg_type: str, role: str) -> bool:
            return msg_type in ("ToolMessage", "FunctionMessage") or role == "tool"

        def _is_human_or_system(msg_type: str, role: str) -> bool:
            return msg_type in ("HumanMessage", "SystemMessage") or role in (
                "user", "system", "human"
            )

        for msg in messages:
            content = ""
            msg_type = ""
            role = ""
            has_tool_calls = False

            if isinstance(msg, dict):
                content = msg.get("content", "") or ""
                role = msg.get("role", "")
                has_tool_calls = bool(msg.get("tool_calls"))
            else:
                msg_type = type(msg).__name__
                content = getattr(msg, "content", "") or ""
                has_tool_calls = bool(getattr(msg, "tool_calls", None))

            # 跳过非 AI 消息
            if _is_tool_message(msg_type, role):
                continue
            if not has_tool_calls and _is_human_or_system(msg_type, role):
                continue

            if content and isinstance(content, str) and content.strip():
                collected.append(content.strip())

        return "\n\n".join(collected)
