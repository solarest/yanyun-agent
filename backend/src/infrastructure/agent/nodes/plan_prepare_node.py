"""基础设施层 - Plan准备节点

LangGraph Node: plan_prepare_node
职责: 从plan_execute工具的结果中解析plan结构并注入state
"""

import logging
from typing import Dict

from langgraph.types import RunnableConfig

from src.domain.entities.agent_state import AgentState
from src.domain.entities.plan import Plan, PlanStep, validate_plan

logger = logging.getLogger(__name__)


async def plan_prepare_node(state: AgentState, config: RunnableConfig) -> dict:
    """Plan准备节点
    
    1. 从最后一条ToolMessage中提取plan_execute的结果
    2. 构建Plan对象
    3. 验证Plan结构
    4. 注入到state中
    
    Args:
        state: 当前Agent状态
        config: LangGraph配置
        
    Returns:
        状态更新字典
    """
    # 子Agent不执行plan
    if state.get("is_sub_agent"):
        logger.warning("Sub-agent should not execute plan")
        return {"error": "Sub-agent cannot execute plan"}

    # 从本轮工具结果中提取plan/plan_execute的结果
    tool_results = state.get("tool_results", {})
    plan_execute_result = None

    for tool_call_id in state.get("last_executed_tool_call_ids", []):
        result = tool_results.get(tool_call_id)
        if result and result.get("metadata", {}).get("type") in ("plan", "plan_execute"):
            plan_execute_result = result
            break

    if not plan_execute_result:
        for result in reversed(list(tool_results.values())):
            if result.get("metadata", {}).get("type") in ("plan", "plan_execute"):
                plan_execute_result = result
                break

    if not plan_execute_result:
        logger.warning("plan result not found in tool_results")
        return {"error": "plan result not found"}
    
    # 从metadata中提取plan信息
    metadata = plan_execute_result.get("metadata", {})
    if metadata.get("type") not in ("plan", "plan_execute"):
        return {"error": "Invalid plan metadata"}
    
    goal = metadata.get("goal")
    execution_order = metadata.get("execution_order")
    steps_list = metadata.get("steps", [])
    
    if not goal or not steps_list:
        return {"error": "Missing plan data in metadata"}

    if not execution_order:
        execution_order = [step["id"] for step in steps_list if "id" in step]
    
    # 构建Plan对象
    steps: Dict[int, PlanStep] = {}
    for step_data in steps_list:
        step_id = step_data["id"]
        steps[step_id] = PlanStep(
            id=step_id,
            description=step_data["description"],
            depends_on=[],  # 简化版:暂不支持依赖
            status="pending",
            result=None,
            sub_agent_task_id=None,
        )
    
    plan: Plan = Plan(
        goal=goal,
        steps=steps,
        execution_order=execution_order,
        current_index=0,
        status="planning",
    )
    
    # 验证Plan结构
    error = validate_plan(plan)
    if error:
        logger.error("Plan validation failed: %s", error)
        return {"error": f"Plan validation failed: {error}"}
    
    logger.info(
        "Plan prepared successfully: goal=%s, steps=%d, execution_order=%s",
        goal,
        len(steps),
        execution_order,
    )
    
    # 返回state更新
    return {
        "plan": plan,
        "plan_results": {},
        "phase": "plan_prepared",
    }
