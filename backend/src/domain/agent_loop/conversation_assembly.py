"""领域服务 - 会话消息到对话消息的转换

将 SessionMessage 聚合实体转换为 ConversationMessage 领域实体，
用于 Prompt 构建域的消息格式转换。
"""

from src.domain.aggregates.session.session_message import (
    SessionMessage,
    SessionMessageRole,
)
from src.domain.entities.conversation import ConversationMessage


class ConversationAssemblyService:
    """将 SessionMessage 持久化聚合转换为 ConversationMessage 领域实体。

    SessionMessage 是持久化聚合实体，ConversationMessage 是 Prompt
    构建域的领域实体。转换时：
    - 历史 assistant 消息不携带 tool_calls（避免缺少对应 tool 结果
      导致 LLM 报错）
    - TOOL_SUMMARY 转为 user 角色消息，标注工具结果上下文
    """

    @staticmethod
    def assemble(
        history_messages: list[SessionMessage],
    ) -> list[ConversationMessage]:
        """将 SessionMessage 列表转换为 ConversationMessage 列表。"""
        result: list[ConversationMessage] = []
        for msg in history_messages:
            if msg.role == SessionMessageRole.USER:
                result.append(ConversationMessage(
                    role="user",
                    content=msg.content,
                ))
            elif msg.role == SessionMessageRole.ASSISTANT:
                # 历史 assistant 消息不携带 tool_calls，
                # 因为对应的 tool 结果消息未完整存储。
                # 工具使用记录以文本摘要形式附在 content 中。
                content_parts = [msg.content or ""]
                if msg.tool_calls:
                    tool_names = list(dict.fromkeys(
                        tc.get("name", "") for tc in msg.tool_calls if tc.get("name")
                    ))
                    if tool_names:
                        tools_summary = f"\n\n[Used Tools: {', '.join(tool_names)}]"
                        content_parts.append(tools_summary)
                result.append(ConversationMessage(
                    role="assistant",
                    content="".join(content_parts),
                ))
            elif msg.role == SessionMessageRole.SYSTEM:
                result.append(ConversationMessage(
                    role="system",
                    content=msg.content,
                ))
            elif msg.role == SessionMessageRole.TOOL_SUMMARY:
                result.append(ConversationMessage(
                    role="user",
                    content=f"[Tool Results] {msg.content}",
                ))
        return result
