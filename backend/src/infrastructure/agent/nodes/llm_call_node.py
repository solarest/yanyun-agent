"""基础设施层 - LLM 调用节点

LangGraph Node: llm_call_node
职责:调用 LLM 并流式输出文本到前端
注意:完整 LLM 入参/出参日志由 infrastructure.llm.callback.LLMCallLogger 负责,
      在真正发起 API 请求的回调中输出,无需在 node 层重复记录。
"""

import asyncio
import logging

from langchain_core.messages import AIMessage, AIMessageChunk, SystemMessage
from langgraph.types import RunnableConfig

from src.domain.agent.agent_state import AgentState
from src.infrastructure.agent.nodes.base_node import BaseNode, NodeContext

logger = logging.getLogger(__name__)


class LLMCallNode(BaseNode):
    """LLM 调用节点"""

    @property
    def node_name(self) -> str:
        return "llm_call"

    @property
    def default_phase(self) -> str:
        return "thinking"

    async def execute(self, state: AgentState, config: RunnableConfig, context: NodeContext) -> dict:
        """执行 LLM 调用

        1. 防御性注入 SystemMessage(如果 state 中有 system_prompt)
        2. 流式调用 LLM(通过 metadata 将上下文透传给 LLMCallLogger)
        3. 发射每个 token (llm-chunk)
        4. 返回累积文本

        Args:
            state: 当前 Agent 状态
            config: LangGraph 配置 (包含 llm, event_service 等)
            context: 节点执行上下文

        Returns:
            状态更新字典
        """
        llm = config["configurable"]["llm"]
        current_turn = context.current_turn + 1

        # 防御性 SystemMessage 注入
        messages = list(state["messages"])
        system_prompt = state.get("system_prompt", "")
        if system_prompt and (not messages or not isinstance(messages[0], SystemMessage)):
            messages = [SystemMessage(content=system_prompt)] + messages
            logger.info(
                "[NODE:llm_call] SystemMessage injected | task_id=%s | turn=%d",
                context.task_id, current_turn
            )

        full_text = ""
        thinking_text = ""  # 深度思考内容
        # 使用 AIMessageChunk 聚合来正确合并流式 tool_call_chunks
        accumulated: AIMessageChunk | None = None

        # 通过 metadata 将业务上下文传入,LLMCallLogger 会在 on_chat_model_start
        # 中读取 metadata,从而关联 agent_id/task_id/turn/node_name。
        llm_call_config = {
            "metadata": {
                "agent_id": context.agent_id,
                "task_id": context.task_id,
                "turn": current_turn,
                "node_name": "llm_call_node",
            }
        }

        # LLM 调用前日志:记录输入信息
        message_count = len(messages)
        has_tool_calls = any(
            hasattr(msg, "tool_calls") and msg.tool_calls
            for msg in messages
        )
        logger.info(
            "[NODE:llm_call] LLM_CALL_INPUT | agent_id=%s | task_id=%s | turn=%d | "
            "message_count=%d | has_tool_calls=%s | system_prompt=%s",
            context.agent_id, context.task_id, current_turn, message_count, has_tool_calls, bool(
                system_prompt)
        )

        # LLM 流式调用超时保护(默认 5 分钟),防止网络异常导致 task 永久挂起
        llm_timeout_sec = config["configurable"].get("llm_timeout_sec", 300)
        try:
            async with asyncio.timeout(llm_timeout_sec):
                async for chunk in llm.astream(messages, config=llm_call_config):
                    # 处理深度思考内容（reasoning_content 字段）
                    if hasattr(chunk, "additional_kwargs") and chunk.additional_kwargs:
                        reasoning = chunk.additional_kwargs.get(
                            "reasoning_content")
                        if reasoning:
                            thinking_text += reasoning
                            # 发射思考内容流式片段
                            await context.event_emitter.emit_thinking_chunk(
                                context.task_id,
                                current_turn,
                                reasoning,
                            )

                    # 处理正常回复内容
                    if chunk.content:
                        full_text += chunk.content
                        # 发射流式片段(走 IEventEmitter 抽象,事件名为 llm:chunk)
                        await context.event_emitter.emit_llm_chunk(
                            context.task_id,
                            current_turn,
                            chunk.content,
                        )

                    # 聚合 chunk 以正确合并 tool_call_chunks
                    if accumulated is None:
                        accumulated = chunk
                    else:
                        accumulated = accumulated + chunk
        except TimeoutError:
            logger.error(
                "[NODE:llm_call] LLM_CALL_ERROR | agent_id=%s | task_id=%s | turn=%d | "
                "error=timeout | timeout_sec=%d",
                context.agent_id, context.task_id, current_turn, llm_timeout_sec,
            )
            return {
                "messages": [AIMessage(content=full_text or "LLM call timed out.")],
                "pending_tool_calls": [],
                "current_llm_text": full_text,
                "phase": "thinking",
                "current_turn": current_turn,
                "error": f"LLM streaming timed out after {llm_timeout_sec}s",
                "should_end": True,
            }

        # 从聚合后的消息中提取完整的 tool_calls
        tool_calls_list = []
        if accumulated and hasattr(accumulated, "tool_calls") and accumulated.tool_calls:
            # 不再过滤无效工具调用,保留给 loop_detect 检测
            tool_calls_list = accumulated.tool_calls

        # 解析 tool_calls 为 pending_tool_calls 格式
        pending_tool_calls = []
        for tc in tool_calls_list:
            pending_tool_calls.append({
                "id": tc.get("id", ""),
                "name": tc.get("name", ""),
                "input": tc.get("args", {}),
            })

        # LLM 调用后日志:记录输出信息
        tool_call_names = [tc.get("name") for tc in pending_tool_calls]
        logger.info(
            "[NODE:llm_call] LLM_CALL_OUTPUT | agent_id=%s | task_id=%s | turn=%d | "
            "response_length=%d | tool_call_count=%d | tool_calls=%s",
            context.agent_id, context.task_id, current_turn, len(full_text), len(
                pending_tool_calls), tool_call_names
        )

        # 发射 LLM 完成事件(与前端 AgentEventStream 约定:llm:complete)
        await context.event_emitter.emit(
            context.task_id,
            "llm:complete",
            {
                "turn": current_turn,
                "fullText": full_text,
                "thinkingText": thinking_text,
                "hasThinking": bool(thinking_text),
                "toolCalls": tool_calls_list,
            },
        )

        # Node 完成日志(将由基类自动记录)
        logger.info(
            "[NODE:llm_call] COMPLETE | agent_id=%s | task_id=%s | turn=%d | "
            "phase=%s | pending_tools=%d | should_end=%s",
            context.agent_id, context.task_id, current_turn,
            "complete" if not pending_tool_calls else "thinking",
            len(pending_tool_calls),
            len(pending_tool_calls) == 0
        )

        # 如果没有 tool_calls,标记任务完成
        should_end = len(pending_tool_calls) == 0
        is_complete = should_end

        # 返回状态更新(包含 pending_tool_calls 供 tool_execute_node 使用)
        return {
            "messages": [
                AIMessage(content=full_text, tool_calls=tool_calls_list or [])
            ],
            "pending_tool_calls": pending_tool_calls,
            # 上一轮工具执行结果在此处失效,避免 observe 误走 Mode B。
            "last_executed_tool_call_ids": [],
            "current_llm_text": full_text,
            "phase": "complete" if is_complete else "thinking",
            "current_turn": current_turn,
            "should_end": should_end,
            "is_complete": is_complete,
        }


# 保持向后兼容的实例导出
llm_call_node = LLMCallNode()
