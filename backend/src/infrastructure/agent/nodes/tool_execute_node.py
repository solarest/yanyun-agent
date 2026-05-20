"""基础设施层 - 工具执行节点

LangGraph Node: tool_execute_node
职责:执行工具调用并返回结果
"""

import asyncio
import logging

from langchain_core.messages import ToolMessage
from langgraph.types import RunnableConfig

from src.domain.entities.agent_state import AgentState
from src.domain.entities.tool import ToolContext
from src.infrastructure.agent.nodes.base_node import BaseNode, NodeContext

logger = logging.getLogger("tool.call")


async def _emit_tool_event(event_emitter, task_id: str, event_type: str, payload: dict) -> None:
    """工具事件只用于 UI/观测，写入失败不能打断工具执行。"""
    if not event_emitter:
        return
    emit_safe = getattr(event_emitter, "emit_safe", None)
    try:
        if callable(emit_safe) and hasattr(type(event_emitter), "emit_safe"):
            await emit_safe(task_id, event_type, payload)
        else:
            await event_emitter.emit(task_id, event_type, payload)
    except Exception as exc:
        logger.warning("tool event emit failed: %s", exc)


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
    tool_context = ToolContext(
        task_id=context.task_id,
        workspace=context.workspace,
        user_id=context.user_id,
        agent_id=context.agent_id,
        extra={
            **context.extra,
            "tool_call_id": tool_call_id,
        },
    )

    # 工具调用前日志
    logger.info(
        "[NODE:tool_execute] TOOL_CALL_INPUT | task_id=%s | tool_call_id=%s | "
        "tool_name=%s | input=%s",
        task_id, tool_call_id, tool_name, tool_input
    )

    await _emit_tool_event(
        event_emitter,
        task_id,
        "tool:call",
        {
            "toolCallId": tool_call_id,
            "toolName": tool_name,
            "input": tool_input,
        },
    )

    try:
        result = await tool_registry.execute(tool_name, tool_input, tool_context)
        status = "success" if result.success else "error"
        result_dict = {
            "tool_name": tool_name,
            "status": status,
            "output": result.output,
            "error": result.error,
            "metadata": result.metadata,
        }

        # 工具调用成功日志
        output_preview = str(result.output)[
            :200] if result.output else "(empty)"
        logger.info(
            "[NODE:tool_execute] TOOL_CALL_SUCCESS | task_id=%s | tool_call_id=%s | "
            "tool_name=%s | status=%s | output_preview=%s",
            task_id, tool_call_id, tool_name, status, output_preview
        )

        await _emit_tool_event(
            event_emitter,
            task_id,
            "tool:result",
            {
                "toolCallId": tool_call_id,
                "toolName": tool_name,
                "status": status,
                "output": result.output,
                "metadata": result.metadata,
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

        # 工具调用失败日志
        logger.error(
            "[NODE:tool_execute] TOOL_CALL_ERROR | task_id=%s | tool_call_id=%s | "
            "tool_name=%s | error=%s",
            task_id, tool_call_id, tool_name, str(e)
        )

        await _emit_tool_event(
            event_emitter,
            task_id,
            "tool:result",
            {
                "toolCallId": tool_call_id,
                "toolName": tool_name,
                "status": "error",
                "error": str(e),
                "metadata": {},
            },
        )
        return tool_call_id, result_dict


class ToolExecuteNode(BaseNode):
    """工具执行节点"""

    @property
    def node_name(self) -> str:
        return "tool_execute"

    @property
    def default_phase(self) -> str:
        return "tool_executing"

    async def execute(self, state: AgentState, config: RunnableConfig, context: NodeContext) -> dict:
        """执行工具调用

        1. 并行执行所有待执行工具调用
        2. 发射工具相关事件
        3. 构建 ToolMessage 列表
        4. 返回工具结果

        Args:
            state: 当前 Agent 状态
            config: LangGraph 配置 (包含 tool_registry, event_emitter, sub_agent_launcher)
            context: 节点执行上下文

        Returns:
            状态更新字典
        """
        tool_registry = config["configurable"]["tool_registry"]
        current_turn = context.current_turn

        # 从 config 获取 sub-agent 相关依赖
        send_message_use_case = config["configurable"].get(
            "send_message_use_case")
        task_repo = config["configurable"].get("task_repo")
        event_emitter = config["configurable"].get("event_emitter")
        session_id = config["configurable"].get("session_id", "")

        # 构建工具 context
        # 如果存在 sub-agent 相关依赖，注入到 extra 中
        tool_context = ToolContext(
            task_id=context.task_id,
            workspace=state.get("workspace", ""),
            agent_id=context.agent_id,
            extra={
                "send_message_use_case": send_message_use_case,
                "task_repo": task_repo,
                "event_emitter": event_emitter,
                "parent_state": state,
                "parent_agent_id": context.agent_id,
                "parent_session_id": session_id,
                "parent_task_id": state.get("parent_task_id") or context.task_id,
            } if send_message_use_case else {},
        )

        pending_tools = state.get("pending_tool_calls", [])
        structured_results = dict(state.get("tool_results", {}))
        awaiting_user_input = False
        final_result = state.get("final_result")
        last_executed_tool_call_ids: list[str] = []

        # Node 入口日志(将由基类自动记录)
        logger.info(
            "[NODE:tool_execute] START | task_id=%s | turn=%d | pending_tools_count=%d | "
            "pending_tools=%s",
            context.task_id, current_turn, len(pending_tools),
            [tc.get("name") for tc in pending_tools]
        )

        if pending_tools:
            # 优先级过滤逻辑:
            # 1. 如果存在 clarify 工具,过滤掉其他工具,只保留 clarify
            # 2. 如果存在 task_create 工具,过滤掉其他工具,只保留 task_create
            # 优先级 1 > 2

            has_clarify = any(tc.get("name") ==
                              "clarify" for tc in pending_tools)
            has_task_create = any(
                tc.get("name") == "task_create" for tc in pending_tools)

            if has_clarify:
                # 优先级 1:只保留 clarify 工具
                pending_tools = [
                    tc for tc in pending_tools if tc.get("name") == "clarify"]
                logger.info(
                    "[NODE:tool_execute] PRIORITY_FILTER | task_id=%s | filter_type=clarify | "
                    "kept_count=%d | filtered_out_count=%d",
                    context.task_id, len(pending_tools),
                    len([tc for tc in state.get("pending_tool_calls", [])
                        if tc.get("name") != "clarify"])
                )
            elif has_task_create:
                # 优先级 2:只保留 task_create 工具
                pending_tools = [tc for tc in pending_tools if tc.get(
                    "name") == "task_create"]
                logger.info(
                    "[NODE:tool_execute] PRIORITY_FILTER | task_id=%s | filter_type=task_create | "
                    "kept_count=%d | filtered_out_count=%d",
                    context.task_id, len(pending_tools),
                    len([tc for tc in state.get("pending_tool_calls", [])
                        if tc.get("name") != "task_create"])
                )
            tasks = [
                _execute_single_tool(
                    tool_registry,
                    context.event_emitter,
                    context.task_id,
                    tc,
                    tool_context,
                )
                for tc in pending_tools
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for i, result in enumerate(results):
                tc = pending_tools[i]
                tool_call_id = tc.get("id", "")
                last_executed_tool_call_ids.append(tool_call_id)
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

        # Node 完成日志(将由基类自动记录)
        success_count = sum(1 for r in structured_results.values()
                            if r.get("status") == "success")
        error_count = sum(1 for r in structured_results.values()
                          if r.get("status") == "error")
        logger.info(
            "[NODE:tool_execute] COMPLETE | task_id=%s | turn=%d | "
            "total_tools=%d | success=%d | error=%d | awaiting_user_input=%s",
            context.task_id, current_turn, len(
                structured_results), success_count, error_count, awaiting_user_input
        )

        # 构建 ToolMessage 列表(LangChain 格式,确保 content 不为 None)
        tool_messages = []
        for tc in pending_tools:
            tool_call_id = tc.get("id", "")
            if tool_call_id not in structured_results:
                continue
            result_entry = structured_results.get(tool_call_id, {})
            content = result_entry.get(
                "output") or result_entry.get("error") or "No result"
            # 防御性保障:LLM provider 不接受 content=None
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
            "last_executed_tool_call_ids": last_executed_tool_call_ids,
            "final_result": final_result,
            "phase": "tool_executing",
        }


# 保持向后兼容的实例导出
tool_execute_node = ToolExecuteNode()
