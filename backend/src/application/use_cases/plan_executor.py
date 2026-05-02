"""应用层 - Plan执行引擎

负责按串行/并行规则调度子Agent执行plan步骤。
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from langgraph.types import RunnableConfig

from src.domain.entities.plan import Plan, PlanStep
from src.domain.entities.agent_state import AgentState

logger = logging.getLogger(__name__)


class PlanExecutor:
    """Plan执行引擎
    
    职责:
    1. 解析execution_order,构建执行流程
    2. 按串行/并行规则创建和调度子Agent
    3. 监控子Agent执行状态
    4. 收集并汇总结果
    """
    
    def __init__(self, max_parallel: int = 5):
        """初始化PlanExecutor
        
        Args:
            max_parallel: 最大并行子Agent数量
        """
        self.max_parallel = max_parallel
        self.semaphore = asyncio.Semaphore(max_parallel)
    
    async def execute_plan(
        self,
        plan: Plan,
        main_agent_state: AgentState,
        main_config: RunnableConfig,
    ) -> Dict[str, Any]:
        """执行plan,返回汇总结果
        
        Args:
            plan: Plan对象
            main_agent_state: 主Agent的state
            main_config: 主Agent的config
            
        Returns:
            汇总结果 {"summary": str, "step_results": dict}
        """
        from src.application.use_cases.send_message import SendMessageUseCase
        
        logger.info(
            "Starting plan execution: goal=%s, steps=%d",
            plan.get("goal"),
            len(plan.get("steps", {})),
        )
        
        # 发射plan创建事件
        event_emitter = (
            main_config["configurable"].get("event_emitter")
            or main_config["configurable"]["event_service"]
        )
        task_id = main_agent_state["task_id"]
        
        await event_emitter.emit(
            task_id,
            "plan:created",
            {
                "plan_id": task_id,
                "goal": plan.get("goal"),
                "execution_order": plan.get("execution_order"),
            },
        )
        
        # 获取SendMessageUseCase实例(用于创建子Agent)
        send_message_use_case = main_config["configurable"].get("send_message_use_case")
        if not send_message_use_case:
            raise ValueError("send_message_use_case not found in config")
        
        step_results: Dict[int, Dict[str, Any]] = {}
        plan["status"] = "executing"
        
        # 遍历execution_order
        for idx, item in enumerate(plan["execution_order"]):
            if isinstance(item, int):
                # 串行执行单个步骤
                logger.info("Executing serial step %d", item)
                result = await self._execute_step(
                    step_id=item,
                    plan=plan,
                    main_state=main_agent_state,
                    main_config=main_config,
                    send_message_use_case=send_message_use_case,
                    previous_step_results=dict(step_results),
                )
                step_results[item] = result
                
            elif isinstance(item, list):
                # 并行执行多个步骤
                logger.info("Executing parallel steps %s", item)
                
                # 发射并行组开始事件
                await event_emitter.emit(
                    task_id,
                    "plan:parallel_group_started",
                    {
                        "step_ids": item,
                    },
                )
                
                # 创建并行任务
                tasks = [
                    self._execute_step_with_semaphore(
                        step_id=sid,
                        plan=plan,
                        main_state=main_agent_state,
                        main_config=main_config,
                        send_message_use_case=send_message_use_case,
                        previous_step_results=dict(step_results),
                    )
                    for sid in item
                ]
                
                # 等待所有并行步骤完成
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # 收集结果
                for i, sid in enumerate(item):
                    if isinstance(results[i], Exception):
                        step_results[sid] = {
                            "status": "failed",
                            "result": None,
                            "error": str(results[i]),
                        }
                        logger.error("Step %d failed: %s", sid, results[i])
                    else:
                        step_results[sid] = results[i]
                
                # 发射并行组完成事件
                await event_emitter.emit(
                    task_id,
                    "plan:parallel_group_completed",
                    {
                        "step_ids": item,
                        "results": {str(k): v for k, v in step_results.items() if k in item},
                    },
                )
        
        # 汇总结果
        summary = self._summarize_results(plan, step_results)
        plan["status"] = (
            "failed"
            if any(r["status"] == "failed" for r in step_results.values())
            else "completed"
        )
        
        # 发射plan完成事件
        await event_emitter.emit(
            task_id,
            "plan:completed",
            {
                "plan_id": task_id,
                "summary": summary,
                "step_results": {str(k): v for k, v in step_results.items()},
            },
        )
        
        logger.info("Plan execution completed: %s", summary)
        
        return {
            "summary": summary,
            "step_results": step_results,
        }
    
    async def _execute_step_with_semaphore(
        self,
        step_id: int,
        plan: Plan,
        main_state: AgentState,
        main_config: RunnableConfig,
        send_message_use_case: Any,
        previous_step_results: Dict[int, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """带信号量控制的步骤执行"""
        async with self.semaphore:
            return await self._execute_step(
                step_id=step_id,
                plan=plan,
                main_state=main_state,
                main_config=main_config,
                send_message_use_case=send_message_use_case,
                previous_step_results=previous_step_results,
            )
    
    async def _execute_step(
        self,
        step_id: int,
        plan: Plan,
        main_state: AgentState,
        main_config: RunnableConfig,
        send_message_use_case: Any,
        previous_step_results: Dict[int, Dict[str, Any]],
    ) -> Dict[str, Any]:
        """执行单个步骤(创建子Agent)"""
        from src.domain.entities.plan import PlanStep
        
        step = plan["steps"].get(step_id)
        if not step:
            return {
                "status": "failed",
                "result": None,
                "error": f"Step {step_id} not found",
            }
        
        task_id = main_state["task_id"]
        event_emitter = (
            main_config["configurable"].get("event_emitter")
            or main_config["configurable"]["event_service"]
        )
        
        # 发射步骤开始事件
        step["status"] = "running"
        await event_emitter.emit(
            task_id,
            "plan:step_started",
            {
                "step_id": step_id,
                "description": step.get("description"),
            },
        )
        
        try:
            # 调用send_message_use_case创建子Agent
            # 注意: 子Agent的执行是同步的,这里需要等待完成
            result = await send_message_use_case._run_sub_agent(
                step=step,
                parent_task_id=task_id,
                workspace=main_state.get("workspace", "/tmp/agent-workspace"),
                agent_id=main_config["configurable"].get("agent_id"),
                model=main_config["configurable"].get("llm_model", "qwen-max"),
                plan_goal=plan.get("goal"),
                previous_step_results=previous_step_results,
            )

            status = "failed" if result.get("error") else "completed"
            step["status"] = status
            step["result"] = result.get("final_result")
            step["sub_agent_task_id"] = result.get("task_id")
            
            # 提取子Agent的执行结果
            step_result = {
                "status": status,
                "result": result.get("final_result") or result.get("error"),
                "error": result.get("error"),
                "sub_agent_task_id": result.get("task_id"),
            }
            
            # 发射步骤完成事件
            await event_emitter.emit(
                task_id,
                "plan:step_completed",
                {
                    "step_id": step_id,
                    "status": status,
                    "result": step_result["result"],
                    "error": step_result["error"],
                    "sub_agent_task_id": step_result["sub_agent_task_id"],
                },
            )
            
            return step_result
            
        except Exception as e:
            logger.exception("Step %d execution failed", step_id)
            
            step_result = {
                "status": "failed",
                "result": None,
                "error": str(e),
            }
            step["status"] = "failed"
            step["result"] = None
            
            # 发射步骤失败事件
            await event_emitter.emit(
                task_id,
                "plan:step_completed",
                {
                    "step_id": step_id,
                    "status": "failed",
                    "error": str(e),
                },
            )
            
            return step_result
    
    def _summarize_results(self, plan: Plan, step_results: Dict[int, Dict[str, Any]]) -> str:
        """汇总所有步骤的结果"""
        total_steps = len(step_results)
        completed_steps = sum(1 for r in step_results.values() if r["status"] == "completed")
        failed_steps = sum(1 for r in step_results.values() if r["status"] == "failed")
        
        summary_parts = [
            f"## Plan Execution Summary",
            f"",
            f"**Goal**: {plan.get('goal')}",
            f"**Total Steps**: {total_steps}",
            f"**Completed**: {completed_steps}",
            f"**Failed**: {failed_steps}",
            f"",
        ]
        
        # 添加各步骤结果摘要
        summary_parts.append("**Step Results**:")
        summary_parts.append("")
        
        for step_id in sorted(step_results.keys()):
            result = step_results[step_id]
            step = plan["steps"].get(step_id, {})
            description = step.get("description", "Unknown")
            
            status_icon = "✓" if result["status"] == "completed" else "✗"
            summary_parts.append(f"{status_icon} **Step {step_id}**: {description}")
            
            if result.get("result"):
                # 截断过长的结果
                result_text = result["result"]
                if len(result_text) > 200:
                    result_text = result_text[:200] + "..."
                summary_parts.append(f"  Result: {result_text}")
            
            if result.get("error"):
                summary_parts.append(f"  Error: {result['error']}")
            
            summary_parts.append("")
        
        if failed_steps > 0:
            summary_parts.append(f"**Warning**: {failed_steps} step(s) failed.")
        else:
            summary_parts.append("**All steps completed successfully.**")
        
        return "\n".join(summary_parts)
