"""基础设施层 - Prompt 上下文组装实现

实现 domain 层定义的 PromptContextInterface SPI。
由 agent-loop 模块调用，负责：
- 将 system_message 和对话历史合并为 LLM API 的 messages 数组
- 对话历史的分组和裁剪（以 MessageGroup 为原子单位）
- 确保工具调用轮次的消息完整性（不拆散 ToolCallRound）
"""

import logging

from src.domain.entities.conversation import ConversationMessage, MessageGroup
from src.domain.interfaces.prompt_context_interface import PromptContextInterface
from src.domain.services.token_utils import count_tokens

logger = logging.getLogger(__name__)


class PromptContextImpl(PromptContextInterface):
    """Prompt 上下文组装实现 — 消息数组模式

    实现对话历史的 Token 预算管理，以 MessageGroup 为原子单位裁剪历史，
    确保工具调用轮次（assistant(tool_calls) + tool(result) × N）不被拆散。
    """

    async def build_messages(
        self,
        system_message: str,
        history: list[ConversationMessage],
        max_tokens: int,
    ) -> list[dict]:
        """构建最终 LLM API messages 数组

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
            LLM API 兼容的 messages 数组
        """
        # 1. 包装 system_message
        system_msg: dict = {"role": "system", "content": system_message}
        system_tokens = count_tokens(system_message)

        # 2. 计算对话历史可用 Token 预算
        available_tokens = max_tokens - system_tokens
        if available_tokens <= 0:
            logger.warning(
                "System message exceeds token budget: system_tokens=%d, max_tokens=%d",
                system_tokens, max_tokens,
            )
            return [system_msg]

        # 3. 裁剪对话历史
        truncated = await self.truncate_history(history, available_tokens)

        # 4. 转换为 API dict 并组装完整数组
        history_msgs = [msg.to_api_message() for msg in truncated]

        full_messages = [system_msg] + history_msgs

        logger.info(
            "Built messages array: total=%d, system_tokens=%d, history_msgs=%d, "
            "history_tokens_est=%d, budget=%d",
            len(full_messages),
            system_tokens,
            len(history_msgs),
            sum(msg.estimate_tokens() for msg in truncated),
            max_tokens,
        )

        return full_messages

    async def truncate_history(
        self,
        history: list[ConversationMessage],
        available_tokens: int,
    ) -> list[ConversationMessage]:
        """裁剪对话历史到 Token 预算内

        以 MessageGroup 为原子单位进行裁剪，确保不拆散工具调用轮次。

        裁剪策略（保护优先级从高到低）：
        1. 最近一轮对话 — 保留当前交互上下文
        2. 最近的工具调用轮次 — 保留近期工具结果
        3. 较早的对话/工具轮次 — 可裁剪

        裁剪算法：
        1. 调用 group_messages() 将 history 分组
        2. 从末尾向前扫描 MessageGroup，累计 token
        3. 当累计 token 超过 available_tokens 时停止
        4. 返回保留的消息列表（保持原始顺序）

        Args:
            history: 完整的对话历史消息列表
            available_tokens: 对话历史的可用 Token 预算

        Returns:
            裁剪后的消息列表
        """
        if not history:
            return []

        # 1. 分组
        groups = self.group_messages(history)

        # 2. 计算每个 group 的 token
        for group in groups:
            group.compute_token_count()

        # 3. 从末尾向前扫描，确定保留哪些 group
        kept_groups: list[MessageGroup] = []
        accumulated = 0

        for group in reversed(groups):
            if accumulated + group.token_count <= available_tokens:
                kept_groups.append(group)
                accumulated += group.token_count
            else:
                # 预算不足，停止扫描（更早的 group 不再保留）
                logger.info(
                    "History truncation: kept %d/%d groups, "
                    "accumulated_tokens=%d/%d",
                    len(kept_groups), len(groups),
                    accumulated, available_tokens,
                )
                break

        # 4. 反转回原始顺序，展平消息列表
        result: list[ConversationMessage] = []
        for group in reversed(kept_groups):
            result.extend(group.messages)

        return result

    def group_messages(
        self,
        messages: list[ConversationMessage],
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
          - dialogue: [assistant]

        Args:
            messages: 对话历史消息列表

        Returns:
            MessageGroup 列表，每个 group 是裁剪时的原子单位
        """
        if not messages:
            return []

        groups: list[MessageGroup] = []
        i = 0

        while i < len(messages):
            msg = messages[i]

            # 检测工具调用轮次：assistant 有 tool_calls → 寻找后续 tool 消息
            if msg.role == "assistant" and msg.tool_calls:
                round_messages: list[ConversationMessage] = [msg]
                i += 1
                # 收集后续的 tool 结果消息
                while i < len(messages) and messages[i].role == "tool":
                    round_messages.append(messages[i])
                    i += 1
                group = MessageGroup(type="tool_call_round",
                                     messages=round_messages)
                group.compute_token_count()
                groups.append(group)
                continue

            # 检测 dialogue 组：连续的 [user, assistant]
            if msg.role == "user":
                dialogue_msgs: list[ConversationMessage] = [msg]
                i += 1
                # 收集后续连续的 assistant（无 tool_calls）
                while i < len(messages) and messages[i].role == "assistant" and not messages[i].tool_calls:
                    dialogue_msgs.append(messages[i])
                    i += 1
                group = MessageGroup(type="dialogue", messages=dialogue_msgs)
                group.compute_token_count()
                groups.append(group)
                continue

            # 孤立的 assistant、system 或其他消息 → 独立 dialogue 组
            solo_msgs: list[ConversationMessage] = [msg]
            i += 1
            group = MessageGroup(type="dialogue", messages=solo_msgs)
            group.compute_token_count()
            groups.append(group)

        return groups
