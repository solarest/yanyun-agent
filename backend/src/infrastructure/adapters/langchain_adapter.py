"""基础设施层 - LangChain 适配器

将领域层消息和工具定义转换为 LangChain 兼容格式。
LangChain 属于外部框架，其类型只应在基础设施层出现。
"""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from src.domain.interfaces.llm_provider import ILLMProvider
from src.domain.repositories.tool_registry import IToolRegistry


class LangChainAdapter:
    """领域消息格式 ↔ LangChain 消息格式的转换适配器。"""

    @staticmethod
    def dict_messages_to_langchain(messages: list[dict]) -> list:
        """将 LLM API dict 消息列表转换为 LangChain 消息对象。

        用于将 PromptContextInterface.build_messages() 的输出
        转换为 LangGraph 可消费的消息格式。
        """
        from langchain_core.messages import ToolMessage as LCMessage

        lc_messages: list = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "system":
                lc_messages.append(SystemMessage(content=content))
            elif role == "user":
                lc_messages.append(HumanMessage(content=content))
            elif role == "assistant":
                lc_messages.append(AIMessage(
                    content=content,
                    tool_calls=msg.get("tool_calls", []),
                ))
            elif role == "tool":
                lc_messages.append(LCMessage(
                    content=content,
                    tool_call_id=msg.get("tool_call_id", ""),
                ))
            else:
                lc_messages.append(HumanMessage(content=content))
        return lc_messages

    @staticmethod
    def tool_defs_to_openai_functions(tool_registry: IToolRegistry) -> list:
        """将工具转换为 OpenAI function schema 格式（供 bind_tools 使用）。"""
        return [tool.to_tool_def().to_llm_schema() for tool in tool_registry.list_tools()]
