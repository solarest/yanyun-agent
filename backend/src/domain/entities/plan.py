"""领域层 - Plan 数据结构定义

定义结构化计划的实体,支持串行+并行混合执行。
"""

from typing import Any, Dict, List, Optional

from typing_extensions import TypedDict


class PlanStep(TypedDict):
    """单个计划步骤"""
    
    id: int
    """步骤ID"""
    
    description: str
    """步骤描述"""
    
    depends_on: List[int]
    """依赖的步骤ID列表"""
    
    status: str
    """执行状态: pending | running | completed | failed"""
    
    result: Optional[str]
    """执行结果"""
    
    sub_agent_task_id: Optional[str]
    """执行的子Agent task_id"""


class Plan(TypedDict):
    """完整的计划结构"""
    
    goal: str
    """计划目标"""
    
    steps: Dict[int, PlanStep]
    """步骤字典 {step_id: PlanStep}"""
    
    execution_order: List[Any]
    """执行顺序,如 [1, [2,3,4], 5]
    
    - 整数表示串行步骤
    - 列表表示并行步骤组
    """
    
    current_index: int
    """当前执行到的索引"""
    
    status: str
    """计划状态: planning | executing | completed | failed"""


def validate_plan(plan: Plan) -> Optional[str]:
    """验证Plan结构的有效性
    
    Args:
        plan: Plan对象
        
    Returns:
        如果验证失败返回错误信息,成功返回None
    """
    # 1. 验证execution_order中的所有step_id都在steps中
    all_step_ids = set(plan["steps"].keys())
    
    def check_execution_order(order: List[Any]) -> Optional[str]:
        for item in order:
            if isinstance(item, int):
                if item not in all_step_ids:
                    return f"Step ID {item} in execution_order not found in steps"
            elif isinstance(item, list):
                for sid in item:
                    if not isinstance(sid, int):
                        return f"Parallel group contains non-integer: {sid}"
                    if sid not in all_step_ids:
                        return f"Step ID {sid} in parallel group not found in steps"
            else:
                return f"Invalid execution_order item type: {type(item)}"
        return None
    
    error = check_execution_order(plan["execution_order"])
    if error:
        return error
    
    # 2. 验证steps中的id是否一致
    for step_id, step in plan["steps"].items():
        if step["id"] != step_id:
            return f"Step ID mismatch: step.id={step['id']} but key={step_id}"
    
    # 3. 验证没有循环依赖(简化版:只检查depends_on中的id是否存在)
    for step in plan["steps"].values():
        for dep_id in step["depends_on"]:
            if dep_id not in all_step_ids:
                return f"Step {step['id']} depends on non-existent step {dep_id}"
    
    return None


def extract_all_step_ids(execution_order: List[Any]) -> List[int]:
    """从execution_order中提取所有step_id
    
    Args:
        execution_order: 执行顺序列表
        
    Returns:
        所有step_id的列表(按出现顺序)
    """
    ids = []
    for item in execution_order:
        if isinstance(item, int):
            ids.append(item)
        elif isinstance(item, list):
            ids.extend(item)
    return ids
