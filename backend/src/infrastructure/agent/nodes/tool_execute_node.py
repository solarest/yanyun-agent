"""基础设施层 - 工具执行节点

LangGraph Node: tool_execute_node
职责：执行工具调用并返回结果
"""

from langchain_core.messages import ToolMessage
from langgraph.types import RunnableConfig

from src.domain.entities.agent_state import AgentState
from src.domain.entities.tool import ToolContext


async def tool_execute_node(state: AgentState, config: RunnableConfig) -> dict:
    """工具执行节点

    1. 遍历待执行工具调用
    2. 执行安全检查
    3. 如需审批则等待
    4. 执行工具
    5. 发射工具相关事件
    6. 返回工具结果

    Args:
        state: 当前 Agent 状态
        config: LangGraph 配置 (包含 tool_registry, event_service)

    Returns:
        状态更新字典
    """
    tool_registry = config["configurable"]["tool_registry"]
    event_svc = config["configurable"]["event_service"]
    task_id = state["task_id"]

    # 构建工具执行上下文
    context = ToolContext(
        task_id=task_id,
        workspace=state.get("workspace", ""),
    )

    pending_tools = state.get("pending_tool_calls", [])
    results = {}

    for tc in pending_tools:
        tool_call_id = tc.get("id", "")
        tool_name = tc.get("name", "")
        tool_input = tc.get("input", {})

        # 发射工具调用开始事件
        await event_svc.emit(
            task_id,
            "tool-call",
            {
                "toolCallId": tool_call_id,
                "toolName": tool_name,
                "input": tool_input,
            },
        )

        # 执行工具
        try:
            result = await tool_registry.execute(tool_name, tool_input, context)
            results[tool_call_id] = result.output
            status = "success" if result.success else "error"
            await event_svc.emit(
                task_id,
                "tool-result",
                {
                    "toolCallId": tool_call_id,
                    "toolName": tool_name,
                    "status": status,
                    "output": result.output,
                },
            )
        except Exception as e:
            results[tool_call_id] = f"Error: {e}"
            await event_svc.emit(
                task_id,
                "tool-result",
                {
                    "toolCallId": tool_call_id,
                    "toolName": tool_name,
                    "status": "error",
                    "error": str(e),
                },
            )

    # 构建 ToolMessage 列表（LangChain 格式，确保与 AIMessage.tool_calls 对应）
    tool_messages = []
    for tc in pending_tools:
        tool_call_id = tc.get("id", "")
        tool_messages.append(
            ToolMessage(
                content=results.get(tool_call_id, "No result"),
                tool_call_id=tool_call_id,
            )
        )

    return {
        "messages": tool_messages,
        "tool_results": results,
        "pending_tool_calls": [],
        "phase": "tool_executing",
    }
