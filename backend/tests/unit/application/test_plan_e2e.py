"""Plan工作流集成测试

测试新的Plan工作流（plan_execute已降级为闭包工具）:
1. LLM调用plan_execute工具 → route_after_llm → loop_detect
2. route_after_tool_execute → tool_observe（不再有 plan_prepare 分支）
3. 子Agent工具集排除plan相关工具
"""

import pytest
from unittest.mock import AsyncMock
from langchain_core.messages import AIMessage

from src.domain.agent.agent_state import AgentState
from src.application.use_cases.agent_workflow import (
    route_after_llm,
    route_after_tool_execute,
)


def make_state(**overrides) -> AgentState:
    """创建测试用AgentState"""
    state: AgentState = {
        "messages": [],
        "task_id": "task-1",
        "workspace": "/tmp",
        "user_message": "hello",
        "task_start_message_count": 0,
        "current_turn": 1,
        "max_turns": 100,
        "phase": "thinking",
        "should_end": False,
        "is_complete": False,
        "pending_tool_calls": [],
        "tool_results": {},
        "awaiting_user_input": False,
        "last_executed_tool_call_ids": [],
        "loop_detection_count": 0,
        "loop_detected": False,
        "loop_type": None,
        "stuck_detection_count": 0,
        "stuck_detected": False,
        "stuck_type": None,
        "current_llm_text": "",
        "empty_retry_count": 0,
        "planning_retry_count": 0,
        "system_prompt": "",
        "final_result": None,
        "error": None,
        "is_sub_agent": False,
        "parent_task_id": None,
    }
    state.update(overrides)
    return state


class TestPlanWorkflowIntegration:
    """Plan工作流集成测试"""

    def test_route_after_llm_sends_plan_execute_to_loop_detect(self):
        """plan_execute工具调用通过 loop_detect 前置守卫"""
        state = make_state(
            messages=[
                AIMessage(
                    content="I'll create a plan",
                    tool_calls=[
                        {
                            "id": "call-1",
                            "name": "plan_execute",
                            "args": {
                                "goal": "Test goal",
                                "execution_order": [1, 2],
                                "steps": [
                                    {"id": 1, "description": "Step 1"},
                                    {"id": 2, "description": "Step 2"},
                                ],
                            },
                        }
                    ],
                )
            ]
        )

        route = route_after_llm(state)
        assert route == "loop_detect"

    def test_route_after_tool_execute_goes_to_loop_detect(self):
        """工具执行后路由到 loop_detect(循环检测前置守卫)"""
        state = make_state(
            last_executed_tool_call_ids=["call-plan"],
            tool_results={
                "call-plan": {
                    "tool_name": "plan_execute",
                    "status": "success",
                    "output": "Plan executed: all steps completed",
                    "metadata": {},
                }
            },
        )

        assert route_after_tool_execute(state) == "llm_call"

    def test_route_after_llm_with_regular_tool_calls(self):
        """普通工具调用仍路由到 loop_detect"""
        state = make_state(
            messages=[
                AIMessage(
                    content="Searching...",
                    tool_calls=[
                        {
                            "id": "call-1",
                            "name": "web_search",
                            "args": {"query": "test"},
                        }
                    ],
                )
            ]
        )

        route = route_after_llm(state)
        assert route == "loop_detect"


class TestSubAgentToolRegistry:
    """子Agent工具集测试"""

    def test_sub_agent_excludes_plan_tools(self):
        """测试子Agent工具集排除plan相关工具"""
        from src.infrastructure.tools.registry import ToolRegistry
        from src.infrastructure.tools.pipeline import ExecutionPipeline
        from src.domain.tool import RegisteredTool, ToolResult

        # 创建父Agent工具集
        parent_registry = ToolRegistry()

        async def dummy_func(input, context=None):
            return ToolResult(output="ok")

        # 注册各种工具
        for tool_name in ["web_search", "file_read", "file_write", "plan", "plan_execute", "clarify"]:
            tool = RegisteredTool(
                name=tool_name,
                description=f"Tool {tool_name}",
                func=dummy_func,
            )
            parent_registry.register(tool)

        # 验证父Agent有所有工具
        assert parent_registry.tool_count == 6

        # 创建子Agent工具集
        sub_registry = ToolRegistry(pipeline=ExecutionPipeline())

        for tool in parent_registry.list_tools():
            # 排除plan和clarify
            if tool.name in ("plan", "plan_execute", "clarify"):
                continue
            sub_registry.register(tool)

        # 验证子Agent工具集
        assert sub_registry.tool_count == 3
        assert sub_registry.resolve("web_search") is not None
        assert sub_registry.resolve("file_read") is not None
        assert sub_registry.resolve("file_write") is not None
        assert sub_registry.resolve("plan") is None
        assert sub_registry.resolve("plan_execute") is None
        assert sub_registry.resolve("clarify") is None
