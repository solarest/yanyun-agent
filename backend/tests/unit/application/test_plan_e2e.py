"""Plan执行端到端集成测试

测试完整的Plan执行流程:
1. LLM调用plan_execute工具
2. plan_prepare节点解析plan
3. plan_execute节点执行plan
4. 子Agent创建和执行
5. 结果汇总
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import AIMessage, ToolMessage, HumanMessage

from src.domain.entities.plan import Plan, PlanStep
from src.domain.entities.agent_state import AgentState
from src.application.use_cases.agent_workflow import (
    route_after_llm,
    route_after_tool_execute,
    AgentWorkflowBuilder,
)
from src.infrastructure.agent.nodes.plan_prepare_node import plan_prepare_node
from src.infrastructure.agent.nodes.plan_execute_node import plan_execute_node


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
        # Plan相关字段
        "plan": None,
        "plan_results": {},
        "is_sub_agent": False,
        "parent_task_id": None,
    }
    state.update(overrides)
    return state


class TestPlanWorkflowIntegration:
    """Plan工作流集成测试"""

    def test_route_after_llm_sends_plan_execute_to_tool_execution(self):
        """plan_execute需要先执行工具,再进入plan_prepare"""
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

    def test_route_after_tool_execute_detects_executed_plan(self):
        """测试plan工具执行完成后路由到plan_prepare"""
        state = make_state(
            last_executed_tool_call_ids=["call-plan"],
            tool_results={
                "call-plan": {
                    "tool_name": "plan",
                    "status": "success",
                    "output": "Plan created",
                    "metadata": {
                        "type": "plan",
                        "goal": "Test goal",
                        "execution_order": [1, 2],
                        "steps": [
                            {"id": 1, "description": "Step 1"},
                            {"id": 2, "description": "Step 2"},
                        ],
                    },
                }
            },
        )

        assert route_after_tool_execute(state) == "plan_prepare"

    def test_route_after_llm_with_regular_tool_calls(self):
        """测试普通工具调用仍路由到loop_detect"""
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

    @pytest.mark.asyncio
    async def test_plan_prepare_node_extracts_plan(self):
        """测试plan_prepare节点能正确解析plan"""
        state = make_state(
            messages=[
                ToolMessage(content="Plan created", tool_call_id="call-1")
            ],
            tool_results={
                "call-1": {
                    "tool_name": "plan_execute",
                    "status": "success",
                    "output": "Plan created",
                    "metadata": {
                        "type": "plan_execute",
                        "goal": "Test goal",
                        "execution_order": [1, [2, 3], 4],
                        "steps": [
                            {"id": 1, "description": "Step 1"},
                            {"id": 2, "description": "Step 2"},
                            {"id": 3, "description": "Step 3"},
                            {"id": 4, "description": "Step 4"},
                        ],
                    },
                }
            },
        )

        config = {"configurable": {}}
        result = await plan_prepare_node(state, config)

        # 验证plan被正确解析
        assert "plan" in result
        plan = result["plan"]
        assert plan["goal"] == "Test goal"
        assert plan["execution_order"] == [1, [2, 3], 4]
        assert len(plan["steps"]) == 4
        assert result["phase"] == "plan_prepared"
        assert "error" not in result

    @pytest.mark.asyncio
    async def test_plan_prepare_node_accepts_plan_tool_metadata(self):
        """测试plan工具的结构化metadata可直接进入执行计划"""
        state = make_state(
            last_executed_tool_call_ids=["call-plan"],
            tool_results={
                "call-plan": {
                    "tool_name": "plan",
                    "status": "success",
                    "output": "Plan created",
                    "metadata": {
                        "type": "plan",
                        "goal": "看看新闻 写成文档",
                        "execution_order": [1, 2],
                        "steps": [
                            {"id": 1, "description": "获取新闻"},
                            {"id": 2, "description": "写入文档"},
                        ],
                    },
                }
            },
        )

        result = await plan_prepare_node(state, {"configurable": {}})

        assert "error" not in result
        assert result["plan"]["goal"] == "看看新闻 写成文档"
        assert result["plan"]["execution_order"] == [1, 2]
        assert result["plan"]["steps"][1]["description"] == "获取新闻"

    @pytest.mark.asyncio
    async def test_plan_prepare_node_rejects_sub_agent(self):
        """测试子Agent不能执行plan"""
        state = make_state(
            is_sub_agent=True,
            messages=[
                ToolMessage(content="Plan created", tool_call_id="call-1")
            ],
            tool_results={
                "call-1": {
                    "tool_name": "plan_execute",
                    "status": "success",
                    "output": "Plan created",
                    "metadata": {
                        "type": "plan_execute",
                        "goal": "Test goal",
                        "execution_order": [1],
                        "steps": [{"id": 1, "description": "Step 1"}],
                    },
                }
            },
        )

        config = {"configurable": {}}
        result = await plan_prepare_node(state, config)

        assert "error" in result
        assert "Sub-agent" in result["error"]

    @pytest.mark.asyncio
    async def test_plan_prepare_node_validates_plan(self):
        """测试plan_prepare节点验证plan结构"""
        state = make_state(
            messages=[
                ToolMessage(content="Plan created", tool_call_id="call-1")
            ],
            tool_results={
                "call-1": {
                    "tool_name": "plan_execute",
                    "status": "success",
                    "output": "Plan created",
                    "metadata": {
                        "type": "plan_execute",
                        "goal": "Test goal",
                        "execution_order": [1, 99],  # 99不存在
                        "steps": [{"id": 1, "description": "Step 1"}],
                    },
                }
            },
        )

        config = {"configurable": {}}
        result = await plan_prepare_node(state, config)

        assert "error" in result
        assert "validation failed" in result["error"].lower()


class TestPlanExecutorIntegration:
    """PlanExecutor集成测试"""

    @pytest.mark.asyncio
    async def test_plan_execute_node_with_mock_executor(self):
        """测试plan_execute节点调用PlanExecutor"""
        plan: Plan = Plan(
            goal="Test goal",
            steps={
                1: PlanStep(
                    id=1,
                    description="Step 1",
                    depends_on=[],
                    status="pending",
                    result=None,
                    sub_agent_task_id=None,
                ),
                2: PlanStep(
                    id=2,
                    description="Step 2",
                    depends_on=[],
                    status="pending",
                    result=None,
                    sub_agent_task_id=None,
                ),
            },
            execution_order=[1, 2],
            current_index=0,
            status="executing",
        )

        state = make_state(
            plan=plan,
            is_sub_agent=False,
        )

        # Mock event emitter
        mock_emitter = AsyncMock()
        
        # Mock PlanExecutor (在函数内导入,需要mock模块)
        import src.application.use_cases.plan_executor as plan_executor_module
        mock_executor = AsyncMock()
        mock_executor.execute_plan.return_value = {
            "summary": "All steps completed",
            "step_results": {
                1: {"status": "completed", "result": "Result 1"},
                2: {"status": "completed", "result": "Result 2"},
            },
        }
        
        with patch.object(plan_executor_module, 'PlanExecutor', return_value=mock_executor):

            config = {
                "configurable": {
                    "event_emitter": mock_emitter,
                    "event_service": mock_emitter,
                    "send_message_use_case": AsyncMock(),
                }
            }

            result = await plan_execute_node(state, config)

            # 验证结果
            assert result["final_result"] == "All steps completed"
            assert result["phase"] == "plan_completed"
            assert result["is_complete"] is True
            assert "error" not in result

            # 验证PlanExecutor被调用
            mock_executor.execute_plan.assert_called_once()


class TestSubAgentToolRegistry:
    """子Agent工具集测试"""

    def test_sub_agent_excludes_plan_tools(self):
        """测试子Agent工具集排除plan相关工具"""
        from src.infrastructure.tools.registry import ToolRegistry
        from src.infrastructure.tools.pipeline import ExecutionPipeline
        from src.domain.entities.tool import RegisteredTool, ToolContext, ToolResult

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


class TestEndToEndPlanFlow:
    """端到端Plan执行流程测试"""

    @pytest.mark.asyncio
    async def test_complete_plan_workflow(self):
        """测试完整的plan工作流: LLM -> plan_prepare -> plan_execute"""
        
        # 步骤1: LLM返回plan_execute工具调用
        state = make_state(
            messages=[
                AIMessage(
                    content="I'll create a plan to complete this task",
                    tool_calls=[
                        {
                            "id": "call-plan",
                            "name": "plan_execute",
                            "args": {
                                "goal": "Research and write report",
                                "execution_order": [1, [2, 3], 4],
                                "steps": [
                                    {"id": 1, "description": "Search for information"},
                                    {"id": 2, "description": "Analyze data part 1"},
                                    {"id": 3, "description": "Analyze data part 2"},
                                    {"id": 4, "description": "Write report"},
                                ],
                            },
                        }
                    ],
                )
            ],
            tool_results={
                "call-plan": {
                    "tool_name": "plan_execute",
                    "status": "success",
                    "output": "Plan created",
                    "metadata": {
                        "type": "plan_execute",
                        "goal": "Research and write report",
                        "execution_order": [1, [2, 3], 4],
                        "steps": [
                            {"id": 1, "description": "Search for information"},
                            {"id": 2, "description": "Analyze data part 1"},
                            {"id": 3, "description": "Analyze data part 2"},
                            {"id": 4, "description": "Write report"},
                        ],
                    },
                }
            },
        )

        # 步骤2: 验证先进入工具执行
        route = route_after_llm(state)
        assert route == "loop_detect"

        # 步骤3: 执行plan_prepare节点
        config = {"configurable": {}}
        prepare_result = await plan_prepare_node(state, config)
        
        assert "plan" in prepare_result
        assert "error" not in prepare_result
        
        # 更新state
        state.update(prepare_result)

        # 步骤4: 验证plan结构
        plan = state["plan"]
        assert plan["goal"] == "Research and write report"
        assert plan["execution_order"] == [1, [2, 3], 4]
        assert len(plan["steps"]) == 4

        # 步骤5: 执行plan_execute节点(使用mock)
        mock_emitter = AsyncMock()
        mock_use_case = AsyncMock()
        mock_use_case._run_sub_agent.return_value = {
            "task_id": "sub-task-1",
            "final_result": "Step completed",
            "error": None,
        }

        # Mock PlanExecutor
        import src.application.use_cases.plan_executor as plan_executor_module
        mock_executor = AsyncMock()
        mock_executor.execute_plan.return_value = {
            "summary": "## Plan Execution Summary\n\n**Goal**: Research and write report\n**Total Steps**: 4\n**Completed**: 4\n**Failed**: 0\n\nAll steps completed successfully.",
            "step_results": {
                1: {"status": "completed", "result": "Search results"},
                2: {"status": "completed", "result": "Analysis 1"},
                3: {"status": "completed", "result": "Analysis 2"},
                4: {"status": "completed", "result": "Report written"},
            },
        }

        with patch.object(plan_executor_module, 'PlanExecutor', return_value=mock_executor):

            config = {
                "configurable": {
                    "event_emitter": mock_emitter,
                    "event_service": mock_emitter,
                    "send_message_use_case": mock_use_case,
                }
            }

            execute_result = await plan_execute_node(state, config)

            # 验证最终结果
            assert "final_result" in execute_result
            assert "Plan Execution Summary" in execute_result["final_result"]
            assert execute_result["phase"] == "plan_completed"
            assert execute_result["is_complete"] is True

            # 验证事件发射(PlanExecutor内部会调用emit)
            # 由于我们mock了PlanExecutor,这里只验证节点执行成功即可
            assert execute_result is not None
