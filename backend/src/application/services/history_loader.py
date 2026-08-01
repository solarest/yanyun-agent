"""应用层 - 历史加载器

封装 5 种模式的历史加载分支（normal / sub-agent / team-leader / team-member / fallback）。
原作 AgentLoopRunner.run() 中步骤 B 的逻辑。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from langchain_core.messages import AIMessage, HumanMessage

from src.domain.aggregates.session.session_message import SessionMessageRole
from src.domain.services.conversation_assembly import ConversationAssemblyService
from src.domain.services.token_utils import resolve_max_context_tokens
from src.infrastructure.adapters.langchain_adapter import LangChainAdapter

if TYPE_CHECKING:
    from src.domain.interfaces.prompt_context_interface import PromptContextInterface
    from src.domain.repositories.session_message_repository import (
        ISessionMessageRepository,
    )

logger = logging.getLogger(__name__)


class HistoryLoader:
    """加载会话历史并构建初始消息列表

    支持 5 种模式:
    - sub-agent: 仅当前任务消息，不继承父 session
    - team-mode leader: 从自有 session 加载历史，不追加入站消息
    - team-mode member: 从自有 session 加载历史 + 追加入站消息
    - normal (with prompt_context): Token 预算管理历史加载
    - fallback (without prompt_context): 简单历史加载
    """

    def __init__(
        self,
        message_repo: ISessionMessageRepository,
        prompt_context: Optional[PromptContextInterface] = None,
    ):
        self._message_repo = message_repo
        self._prompt_context = prompt_context

    async def load(
        self,
        session_id: str,
        system_prompt: str,
        model: str,
        content: str,
        is_sub_agent: bool = False,
        team_mode: bool = False,
        team_role: Optional[str] = None,
        default_model: str = "gpt-4",
    ) -> list:
        """加载历史消息

        Args:
            session_id: 会话 ID
            system_prompt: 已构建的 system prompt
            model: LLM 模型名称
            content: 用户消息内容
            is_sub_agent: 是否为 sub-agent 模式
            team_mode: 是否为 team mode
            team_role: team 角色 ("leader" | "member")
            default_model: 默认模型名

        Returns:
            LangChain 消息列表
        """
        if is_sub_agent:
            # Sub-agent: 只接收本次原子任务
            return [HumanMessage(content=content)]

        if team_mode:
            messages = await self._load_team_mode(
                session_id, system_prompt, model, content, team_role, default_model,
            )
        elif self._prompt_context:
            messages = await self._load_with_prompt_context(
                session_id, system_prompt, model, default_model,
            )
        else:
            # 降级：简单历史加载
            messages = await self._load_fallback(session_id)

        # 追加当前用户消息（用户消息延迟写入文件后，DB 历史中不再包含当前消息）
        messages.append(HumanMessage(content=content))
        return messages

    async def _load_team_mode(
        self,
        session_id: str,
        system_prompt: str,
        model: str,
        content: str,
        team_role: Optional[str],
        default_model: str,
    ) -> list:
        """Team mode 历史加载"""
        if self._prompt_context:
            history_messages = await self._message_repo.list_by_session(
                session_id, limit=100
            )
            conversation_history = ConversationAssemblyService.assemble(
                history_messages
            )
            max_context_tokens = resolve_max_context_tokens(model or default_model)
            initial_history_budget = int(max_context_tokens * 0.25)
            api_messages = await self._prompt_context.build_messages(
                system_message=system_prompt,
                history=conversation_history,
                max_tokens=initial_history_budget,
            )
            messages = LangChainAdapter.dict_messages_to_langchain(api_messages)
        else:
            messages = await self._load_fallback(session_id)

        return messages

    async def _load_with_prompt_context(
        self,
        session_id: str,
        system_prompt: str,
        model: str,
        default_model: str,
    ) -> list:
        """Token 预算管理的历史加载"""
        history_messages = await self._message_repo.list_by_session(
            session_id, limit=100
        )
        conversation_history = ConversationAssemblyService.assemble(
            history_messages
        )
        max_context_tokens = resolve_max_context_tokens(model or default_model)
        initial_history_budget = int(max_context_tokens * 0.25)
        api_messages = await self._prompt_context.build_messages(
            system_message=system_prompt,
            history=conversation_history,
            max_tokens=initial_history_budget,
        )
        return LangChainAdapter.dict_messages_to_langchain(api_messages)

    async def _load_fallback(self, session_id: str) -> list:
        """降级方案：无 PromptContextInterface 时的简单历史加载"""
        messages: list = []
        history_messages = await self._message_repo.list_by_session(
            session_id, limit=20
        )
        for msg in history_messages:
            if msg.role == SessionMessageRole.USER:
                messages.append(HumanMessage(content=msg.content))
            elif msg.role == SessionMessageRole.ASSISTANT:
                content_parts = [msg.content or ""]
                if msg.tool_calls:
                    tool_names = list(dict.fromkeys(
                        tc.get("name", "") for tc in msg.tool_calls if tc.get("name")
                    ))
                    if tool_names:
                        tools_summary = f"\n\n[Used Tools: {', '.join(tool_names)}]"
                        content_parts.append(tools_summary)
                messages.append(
                    AIMessage(content="".join(content_parts)))
            elif msg.role == SessionMessageRole.TOOL_SUMMARY:
                messages.append(HumanMessage(
                    content=f"[Tool Results] {msg.content}"))
        return messages
