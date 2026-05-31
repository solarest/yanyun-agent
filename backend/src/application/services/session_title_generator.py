"""应用层 - 会话标题生成服务

使用 LLM 为会话自动生成简洁标题。
"""

import logging

from src.domain.interfaces.llm_provider import ILLMProvider
from src.domain.repositories.session_repository import ISessionRepository

logger = logging.getLogger(__name__)


class SessionTitleGenerator:
    """使用 LLM 自动生成会话标题。

    在用户发送首条消息时异步调用，不阻塞主流程。
    如果 LLM 生成失败，降级为截取用户消息前段作为标题。
    """

    def __init__(
        self,
        llm_provider: Optional[ILLMProvider],
        session_repo: ISessionRepository,
    ):
        self.llm_provider = llm_provider
        self.session_repo = session_repo

    async def generate(self, session_id: str, user_message: str) -> None:
        """使用 LLM 生成会话标题。

        Args:
            session_id: 会话 ID
            user_message: 用户的第一条消息
        """
        try:
            from langchain_core.prompts import PromptTemplate

            if not self.llm_provider:
                logger.warning(
                    "LLM Provider not configured, skipping title generation")
                return

            # 创建 LLM 实例（不绑定工具）
            llm = self.llm_provider.create_chat_model()

            # 构建提示词
            prompt = PromptTemplate.from_template(
                "请根据用户的消息内容，生成一个简洁的会话标题（不超过15个中文字符或30个英文字符）。\n"
                "要求：\n"
                "1. 准确概括用户的核心需求或意图\n"
                "2. 简洁明了，适合作为会话列表的显示标题\n"
                "3. 只返回标题文本，不要添加任何解释或其他内容\n\n"
                "用户消息：{message}\n\n"
                "标题："
            )

            # 调用 LLM
            # 限制输入长度
            response = await llm.ainvoke(prompt.format(message=user_message[:500]))

            # 提取标题（去除前后空白和可能的引号）
            title = response.content.strip().strip('"').strip("'")

            # 限制标题长度
            if len(title) > 30:
                title = title[:30].rstrip()

            # 更新会话标题
            session = await self.session_repo.get_by_id(session_id)
            if session and not session.title:  # 只在还没有标题时更新
                session.title = title
                await self.session_repo.update(session)
                logger.info("Generated session title: %s", title)

        except Exception as e:
            logger.exception("Failed to generate session title: %s", e)
            # 如果生成失败，使用默认的截取方式
            session = await self.session_repo.get_by_id(session_id)
            if session and not session.title:
                session.auto_title(user_message)
                await self.session_repo.update(session)
