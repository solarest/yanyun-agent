"""基础设施层 - 工具执行节点

LangGraph Node: tool_execute_node
职责：执行工具调用并返回结果
"""

import asyncio
import logging

from langchain_core.messages import ToolMessage
from langgraph.types import RunnableConfig

from src.domain.entities.agent_state import AgentState
from src.domain.entities.tool import ToolContext

logger = logging.getLogger("tool.call")


async def _execute_single_tool(
    tool_registry,
    event_emitter,
    task_id: str,
    tc: dict,
    context: ToolContext,
) -> tuple[str, dict]:
    """执行单个工具调用，返回 (tool_call_id, result_dict)"""
    tool_call_id = tc.get("id", "")
    tool_name = tc.get("name", "")
    tool_input = tc.get("input", {})

    await event_emitter.emit(
        task_id,
        "tool:call",
        {
            "toolCallId": tool_call_id,
            "toolName": tool_name,
            "input": tool_input,
        },
    )

    try:
        result = await tool_registry.execute(tool_name, tool_input, context)
        status = "success" if result.success else "error"
        result_dict = {
            "tool_name": tool_name,
            "status": status,
            "output": result.output,
            "error": result.error,
            "metadata": result.metadata,
        }
        await event_emitter.emit(
            task_id,
            "tool:result",
            {
                "toolCallId": tool_call_id,
                "toolName": tool_name,
                "status": status,
                "output": result.output,
            },
        )
        return tool_call_id, result_dict
    except Exception as e:
        result_dict = {
            "tool_name": tool_name,
            "status": "error",
            "output": None,
            "error": str(e),
            "metadata": {},
        }
        await event_emitter.emit(
            task_id,
            "tool:result",
            {
                "toolCallId": tool_call_id,
                "toolName": tool_name,
                "status": "error",
                "error": str(e),
            },
        )
        return tool_call_id, result_dict


async def tool_execute_node(state: AgentState, config: RunnableConfig) -> dict:
    """工具执行节点

    1. 并行执行所有待执行工具调用
    2. 发射工具相关事件
    3. 构建 ToolMessage 列表
    4. 返回工具结果

    Args:
        state: 当前 Agent 状态
        config: LangGraph 配置 (包含 tool_registry, event_emitter)

    Returns:
        状态更新字典
    """
    tool_registry = config["configurable"]["tool_registry"]
    event_emitter = (
        config["configurable"].get("event_emitter")
        or config["configurable"]["event_service"]
    )
    task_id = state["task_id"]
    current_turn = state.get("current_turn", 0)

    await event_emitter.emit_phase_changed(
        task_id,
        "tool_executing",
        state.get("phase", "thinking"),
        current_turn,
    )

    context = ToolContext(
        task_id=task_id,
        workspace=state.get("workspace", ""),
        agent_id=config["configurable"].get("agent_id"),
    )

    pending_tools = state.get("pending_tool_calls", [])
    structured_results = dict(state.get("tool_results", {}))
    awaiting_user_input = False
    final_result = state.get("final_result")

    # 并行执行所有工具调用
    if pending_tools:
        tasks = [
            _execute_single_tool(
                tool_registry, event_emitter, task_id, tc, context
            )
            for tc in pending_tools
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            tc = pending_tools[i]
            tool_call_id = tc.get("id", "")
            if isinstance(result, Exception):
                # asyncio.gather 异常兜底
                logger.exception(
                    "Unexpected error executing tool %s: %s",
                    tc.get("name", ""), result,
                )
                structured_results[tool_call_id] = {
                    "tool_name": tc.get("name", ""),
                    "status": "error",
                    "output": None,
                    "error": str(result),
                    "metadata": {},
                }
            else:
                call_id, result_dict = result
                structured_results[call_id] = result_dict
                if result_dict.get("metadata", {}).get("awaiting_user_input"):
                    awaiting_user_input = True
                    final_result = result_dict.get("output")

    # 构建 ToolMessage 列表（LangChain 格式，确保 content 不为 None）
    tool_messages = []
    for tc in pending_tools:
        tool_call_id = tc.get("id", "")
        result_entry = structured_results.get(tool_call_id, {})
        content = result_entry.get("output") or result_entry.get("error") or "No result"
        # 防御性保障：LLM provider 不接受 content=None
        if not isinstance(content, str):
            content = str(content)
        tool_messages.append(
            ToolMessage(content=content, tool_call_id=tool_call_id)
        )

    return {
        "messages": tool_messages,
        "tool_results": structured_results,
        "pending_tool_calls": [],
        "awaiting_user_input": awaiting_user_input,
        "final_result": final_result,
        "phase": "tool_executing",
    }
