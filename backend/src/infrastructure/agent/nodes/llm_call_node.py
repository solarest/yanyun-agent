"""基础设施层 - LLM 调用节点

LangGraph Node: llm_call_node
职责：调用 LLM 并流式输出文本到前端
"""

import json
import logging

from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, SystemMessage
from langgraph.types import RunnableConfig

from src.domain.entities.agent_state import AgentState

# 独立的 LLM 调用日志记录器（记录模型信息、完整输入与完整输出）
llm_logger = logging.getLogger("llm.call")


def _get_model_info(llm) -> dict:
    """提取 LLM 模型信息（provider/model/temperature 等）"""
    info: dict = {}
    for attr in ("model_name", "model", "model_id"):
        value = getattr(llm, attr, None)
        if value:
            info["model"] = value
            break
    for attr in ("temperature", "max_tokens", "top_p"):
        value = getattr(llm, attr, None)
        if value is not None:
            info[attr] = value
    # 尝试提取 provider 类名
    info["class"] = type(llm).__name__
    return info


def _serialize_messages(messages: list[BaseMessage]) -> list[dict]:
    """将消息列表序列化为可读的 dict 列表（保留完整内容）"""
    result = []
    for msg in messages:
        item: dict = {
            "role": getattr(msg, "type", msg.__class__.__name__),
            "content": msg.content,
        }
        # 工具调用请求（AIMessage.tool_calls）
        tool_calls = getattr(msg, "tool_calls", None)
        if tool_calls:
            item["tool_calls"] = tool_calls
        # 工具返回结果（ToolMessage）
        tool_call_id = getattr(msg, "tool_call_id", None)
        if tool_call_id:
            item["tool_call_id"] = tool_call_id
        name = getattr(msg, "name", None)
        if name:
            item["name"] = name
        result.append(item)
    return result


async def llm_call_node(state: AgentState, config: RunnableConfig) -> dict:
    """LLM 调用节点

    1. 发射阶段变更事件
    2. 防御性注入 SystemMessage（如果 state 中有 system_prompt）
    3. 流式调用 LLM
    4. 发射每个 token (llm-chunk)
    5. 返回累积文本

    Args:
        state: 当前 Agent 状态
        config: LangGraph 配置 (包含 llm, event_service 等)

    Returns:
        状态更新字典
    """
    llm = config["configurable"]["llm"]
    event_svc = config["configurable"]["event_service"]
    task_id = state["task_id"]
    current_turn = state.get("current_turn", 0) + 1

    # 发射阶段变更事件
    await event_svc.emit(
        task_id,
        "phase-changed",
        {
            "phase": "thinking",
            "previousPhase": state.get("phase", "idle"),
            "turn": current_turn,
        },
    )

    # 防御性 SystemMessage 注入
    messages = list(state["messages"])
    system_prompt = state.get("system_prompt", "")
    if system_prompt and (not messages or not isinstance(messages[0], SystemMessage)):
        messages = [SystemMessage(content=system_prompt)] + messages

    # === LLM 调用日志：记录模型信息与完整输入 ===
    model_info = _get_model_info(llm)
    llm_logger.info(
        "[LLM-CALL] task_id=%s turn=%s model_info=%s input=%s",
        task_id,
        current_turn,
        json.dumps(model_info, ensure_ascii=False, default=str),
        json.dumps(_serialize_messages(messages), ensure_ascii=False, default=str),
    )

    full_text = ""
    # 使用 AIMessageChunk 聚合来正确合并流式 tool_call_chunks
    accumulated: AIMessageChunk | None = None

    async for chunk in llm.astream(messages):
        if chunk.content:
            full_text += chunk.content
            # 发射流式片段
            await event_svc.emit(
                task_id,
                "llm-chunk",
                {
                    "turn": current_turn,
                    "text": chunk.content,
                    "delta": True,
                },
            )

        # 聚合 chunk 以正确合并 tool_call_chunks
        if accumulated is None:
            accumulated = chunk
        else:
            accumulated = accumulated + chunk

    # 从聚合后的消息中提取完整的 tool_calls
    tool_calls_list = []
    if accumulated and hasattr(accumulated, "tool_calls") and accumulated.tool_calls:
        # 过滤掉无效的工具调用（无名称或无 ID）
        tool_calls_list = [
            tc for tc in accumulated.tool_calls
            if tc.get("name") and tc.get("id")
        ]

    # 解析 tool_calls 为 pending_tool_calls 格式
    pending_tool_calls = []
    for tc in tool_calls_list:
        pending_tool_calls.append({
            "id": tc.get("id", ""),
            "name": tc.get("name", ""),
            "input": tc.get("args", {}),
        })

    # === LLM 调用日志：记录完整输出 ===
    usage_metadata = getattr(accumulated, "usage_metadata", None) if accumulated else None
    response_metadata = getattr(accumulated, "response_metadata", None) if accumulated else None
    llm_logger.info(
        "[LLM-CALL] task_id=%s turn=%s model=%s output=%s",
        task_id,
        current_turn,
        model_info.get("model"),
        json.dumps(
            {
                "content": full_text,
                "tool_calls": tool_calls_list,
                "usage": usage_metadata,
                "response_metadata": response_metadata,
            },
            ensure_ascii=False,
            default=str,
        ),
    )

    # 发射 LLM 完成事件
    await event_svc.emit(
        task_id,
        "llm-complete",
        {
            "turn": current_turn,
            "fullText": full_text,
            "toolCalls": tool_calls_list,
        },
    )

    # 返回状态更新（包含 pending_tool_calls 供 tool_execute_node 使用）
    return {
        "messages": [
            AIMessage(content=full_text, tool_calls=tool_calls_list or [])
        ],
        "pending_tool_calls": pending_tool_calls,
        "current_llm_text": full_text,
        "phase": "thinking",
        "current_turn": current_turn,
    }
