"""基础设施层 - LLM 调用节点

LangGraph Node: llm_call_node
职责：调用 LLM 并流式输出文本到前端
注意：完整 LLM 入参/出参日志由 infrastructure.llm.callback.LLMCallLogger 负责，
      在真正发起 API 请求的回调中输出，无需在 node 层重复记录。
"""

import asyncio
import logging

from langchain_core.messages import AIMessage, AIMessageChunk, SystemMessage
from langgraph.types import RunnableConfig

from src.domain.entities.agent_state import AgentState

logger = logging.getLogger(__name__)


async def llm_call_node(state: AgentState, config: RunnableConfig) -> dict:
    """LLM 调用节点

    1. 发射阶段变更事件
    2. 防御性注入 SystemMessage（如果 state 中有 system_prompt）
    3. 流式调用 LLM（通过 metadata 将上下文透传给 LLMCallLogger）
    4. 发射每个 token (llm-chunk)
    5. 返回累积文本

    Args:
        state: 当前 Agent 状态
        config: LangGraph 配置 (包含 llm, event_service 等)

    Returns:
        状态更新字典
    """
    llm = config["configurable"]["llm"]
    event_emitter = (
        config["configurable"].get("event_emitter")
        or config["configurable"]["event_service"]
    )
    agent_id = config["configurable"].get("agent_id", "unknown")
    task_id = state["task_id"]
    current_turn = state.get("current_turn", 0) + 1
    previous_phase = state.get("phase", "idle")

    # Node 入口日志
    logger.info(
        "[NODE:llm_call] START | agent_id=%s | task_id=%s | turn=%d | previous_phase=%s",
        agent_id, task_id, current_turn, previous_phase
    )

    # 发射阶段变更事件（走 IEventEmitter 抽象，事件名为 phase:changed）
    await event_emitter.emit_phase_changed(
        task_id,
        "thinking",
        previous_phase,
        current_turn,
    )

    # 防御性 SystemMessage 注入
    messages = list(state["messages"])
    system_prompt = state.get("system_prompt", "")
    if system_prompt and (not messages or not isinstance(messages[0], SystemMessage)):
        messages = [SystemMessage(content=system_prompt)] + messages
        logger.info(
            "[NODE:llm_call] SystemMessage injected | task_id=%s | turn=%d",
            task_id, current_turn
        )

    full_text = ""
    # 使用 AIMessageChunk 聚合来正确合并流式 tool_call_chunks
    accumulated: AIMessageChunk | None = None

    # 通过 metadata 将业务上下文传入，LLMCallLogger 会在 on_chat_model_start
    # 中读取 metadata，从而关联 agent_id/task_id/turn/node_name。
    llm_call_config = {
        "metadata": {
            "agent_id": agent_id,
            "task_id": task_id,
            "turn": current_turn,
            "node_name": "llm_call_node",
        }
    }

    # LLM 调用前日志：记录输入信息
    message_count = len(messages)
    has_tool_calls = any(
        hasattr(msg, "tool_calls") and msg.tool_calls
        for msg in messages
    )
    logger.info(
        "[NODE:llm_call] LLM_CALL_INPUT | agent_id=%s | task_id=%s | turn=%d | "
        "message_count=%d | has_tool_calls=%s | system_prompt=%s",
        agent_id, task_id, current_turn, message_count, has_tool_calls, bool(
            system_prompt)
    )

    # LLM 流式调用超时保护（默认 5 分钟），防止网络异常导致 task 永久挂起
    llm_timeout_sec = config["configurable"].get("llm_timeout_sec", 300)
    try:
        async with asyncio.timeout(llm_timeout_sec):
            async for chunk in llm.astream(messages, config=llm_call_config):
                if chunk.content:
                    full_text += chunk.content
                    # 发射流式片段（走 IEventEmitter 抽象，事件名为 llm:chunk）
                    await event_emitter.emit_llm_chunk(
                        task_id,
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
            agent_id, task_id, current_turn, llm_timeout_sec,
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
        # 不再过滤无效工具调用，保留给 loop_detect 检测
        tool_calls_list = accumulated.tool_calls

    # 解析 tool_calls 为 pending_tool_calls 格式
    pending_tool_calls = []
    for tc in tool_calls_list:
        pending_tool_calls.append({
            "id": tc.get("id", ""),
            "name": tc.get("name", ""),
            "input": tc.get("args", {}),
        })

    # LLM 调用后日志：记录输出信息
    tool_call_names = [tc.get("name") for tc in pending_tool_calls]
    logger.info(
        "[NODE:llm_call] LLM_CALL_OUTPUT | agent_id=%s | task_id=%s | turn=%d | "
        "response_length=%d | tool_call_count=%d | tool_calls=%s",
        agent_id, task_id, current_turn, len(full_text), len(
            pending_tool_calls), tool_call_names
    )

    # 发射 LLM 完成事件（与前端 AgentEventStream 约定：llm:complete）
    await event_emitter.emit(
        task_id,
        "llm:complete",
        {
            "turn": current_turn,
            "fullText": full_text,
            "toolCalls": tool_calls_list,
        },
    )

    # Node 完成日志
    logger.info(
        "[NODE:llm_call] COMPLETE | agent_id=%s | task_id=%s | turn=%d | "
        "phase=thinking | pending_tools=%d",
        agent_id, task_id, current_turn, len(pending_tool_calls)
    )

    # 返回状态更新（包含 pending_tool_calls 供 tool_execute_node 使用）
    return {
        "messages": [
            AIMessage(content=full_text, tool_calls=tool_calls_list or [])
        ],
        "pending_tool_calls": pending_tool_calls,
        # 上一轮工具执行结果在此处失效，避免 observe 误走 Mode B。
        "last_executed_tool_call_ids": [],
        "current_llm_text": full_text,
        "phase": "thinking",
        "current_turn": current_turn,
    }
