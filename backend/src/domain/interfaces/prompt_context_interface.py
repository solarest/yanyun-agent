"""领域层 - Prompt 上下文组装接口（SPI）

本接口定义了对话历史管理的契约，由 infrastructure 层的 agent-loop 模块实现。
遵循 DDD 的依赖倒置原则：领域层定义接口，基础设施层提供实现。
"""

from abc import ABC, abstractmethod
from src.domain.conversation.conversation import ConversationMessage, MessageGroup


class PromptContextInterface(ABC):
    """Prompt 上下文组装接口 — 消息数组模式

    本接口定义了运行域对话历史管理的契约。由 agent-loop 模块实现，负责：
    - 将 system_message 和对话历史合并为 LLM API 的 messages 数组
    - 对话历史的分组和裁剪（以 MessageGroup 为原子单位）
    - 确保工具调用轮次的消息完整性（不拆散 ToolCallRound）
    """

    @abstractmethod
    async def build_messages(
        self,
        system_message: str,
        history: list[ConversationMessage],
        max_tokens: int
    ) -> list[dict]:
        """构建最终 LLM API messages 数组

        这是 agent-loop 调用 LLM 前的最后一步，将系统消息和对话历史
        合并为符合 LLM API 协议的 messages 数组。

        处理流程：
        1. 将 system_message 包装为 {"role": "system", "content": ...}
        2. 计算 system_message 的 token 数，得到对话历史的可用预算
        3. 调用 truncate_history() 裁剪历史到预算内
        4. 将裁剪后的 ConversationMessage 列表通过 to_api_message() 转为 dict
        5. 返回 [system_msg, ...history_msgs] 的完整数组

        Args:
            system_message: PromptAssembleService 输出的 11 层系统消息
            history: 对话历史消息列表
            max_tokens: 整个 messages 数组的最大 Token 预算

        Returns:
            LLM API 兼容的 messages 数组，格式：
            [
                {"role": "system", "content": "..."},
                {"role": "user", "content": "..."},
                {"role": "assistant", "content": "...", "tool_calls": [...]},
                {"role": "tool", "tool_call_id": "...", "content": "..."},
                ...
            ]
        """
        pass

    @abstractmethod
    async def truncate_history(
        self,
        history: list[ConversationMessage],
        available_tokens: int
    ) -> list[ConversationMessage]:
        """裁剪对话历史到 Token 预算内

        以 MessageGroup 为原子单位进行裁剪，确保不拆散工具调用轮次。

        裁剪策略（保护优先级从高到低）：
        1. system_message — 永不裁剪（不在本方法范围内，已从预算中扣除）
        2. 最近一轮对话 — 保留当前交互上下文
        3. 最近的工具调用轮次 — 保留近期工具结果
        4. 较早的对话/工具轮次 — 可裁剪

        裁剪算法：
        1. 调用 group_messages() 将 history 分组
        2. 从末尾向前扫描 MessageGroup，累计 token
        3. 当累计 token 接近 available_tokens 时停止
        4. 返回保留的消息列表（保持原始顺序）

        Args:
            history: 完整的对话历史消息列表
            available_tokens: 对话历史的可用 Token 预算
                （= max_tokens - system_message_tokens）

        Returns:
            裁剪后的消息列表
        """
        pass

    @abstractmethod
    def group_messages(
        self,
        messages: list[ConversationMessage]
    ) -> list[MessageGroup]:
        """将消息列表分组为逻辑单元

        分组规则：
        - dialogue 组：连续的 [user, assistant]（assistant 无 tool_calls）
        - tool_call_round 组：[assistant(有 tool_calls), tool(result) × N]
        - 单独的 user/assistant 消息形成独立的 dialogue 组

        分组示例：
        输入消息序列：[user, assistant, user, assistant(tc), tool, tool, assistant]
        分组结果：
          - dialogue: [user, assistant]
          - tool_call_round: [assistant(tc), tool, tool]
          - dialogue: [assistant]  （工具调用后的继续回复，归入下一组或独立）

        Args:
            messages: 对话历史消息列表

        Returns:
            MessageGroup 列表，每个 group 是裁剪时的原子单位
        """
        pass
