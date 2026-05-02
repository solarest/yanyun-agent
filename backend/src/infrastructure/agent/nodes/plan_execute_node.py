"""基础设施层 - Plan执行节点

LangGraph Node: plan_execute_node
职责: 执行plan,等待所有子任务完成,汇总结果
"""

import logging

from langgraph.types import RunnableConfig

from src.domain.entities.agent_state import AgentState
from src.domain.entities.plan import Plan

logger = logging.getLogger(__name__)


async def plan_execute_node(state: AgentState, config: RunnableConfig) -> dict:
    """Plan执行节点
    
    1. 检测state中是否有plan
    2. 如果有,调用PlanExecutor执行
    3. 等待所有子任务完成
    4. 汇总结果到final_result
    
    Args:
        state: 当前Agent状态
        config: LangGraph配置(包含send_message_use_case)
        
    Returns:
        状态更新字典
    """
    plan = state.get("plan")
    if not plan:
        logger.warning("No plan found in state")
        return {}
    
    # 子Agent不执行plan
    if state.get("is_sub_agent"):
        logger.warning("Sub-agent should not execute plan")
        return {}
    
    logger.info("Executing plan: %s", plan.get("goal"))
    
    # 导入PlanExecutor
    from src.application.use_cases.plan_executor import PlanExecutor
    
    # 创建执行器
    executor = PlanExecutor(max_parallel=5)
    
    try:
        # 执行plan
        result = await executor.execute_plan(
            plan=plan,
            main_agent_state=state,
            main_config=config,
        )
        
        logger.info("Plan execution completed: %s", result.get("summary"))
        
        return {
            "final_result": result["summary"],
            "plan_results": result["step_results"],
            "phase": "plan_completed",
            "is_complete": True,
        }
        
    except Exception as e:
        logger.exception("Plan execution failed")
        return {
            "error": f"Plan execution failed: {e}",
            "phase": "plan_failed",
            "should_end": True,
        }
