"""Plan数据结构和验证逻辑的单元测试"""

import pytest

from src.domain.entities.plan import Plan, PlanStep, validate_plan, extract_all_step_ids


class TestPlanValidation:
    """Plan结构验证测试"""
    
    def test_valid_plan_with_serial_steps(self):
        """验证纯串行步骤的plan"""
        plan: Plan = Plan(
            goal="Test goal",
            steps={
                1: PlanStep(id=1, description="Step 1", depends_on=[], status="pending", result=None, sub_agent_task_id=None),
                2: PlanStep(id=2, description="Step 2", depends_on=[], status="pending", result=None, sub_agent_task_id=None),
            },
            execution_order=[1, 2],
            current_index=0,
            status="planning",
        )
        
        error = validate_plan(plan)
        assert error is None
    
    def test_valid_plan_with_parallel_steps(self):
        """验证包含并行步骤的plan"""
        plan: Plan = Plan(
            goal="Test goal",
            steps={
                1: PlanStep(id=1, description="Step 1", depends_on=[], status="pending", result=None, sub_agent_task_id=None),
                2: PlanStep(id=2, description="Step 2", depends_on=[], status="pending", result=None, sub_agent_task_id=None),
                3: PlanStep(id=3, description="Step 3", depends_on=[], status="pending", result=None, sub_agent_task_id=None),
            },
            execution_order=[1, [2, 3]],
            current_index=0,
            status="planning",
        )
        
        error = validate_plan(plan)
        assert error is None
    
    def test_valid_plan_mixed_serial_parallel(self):
        """验证混合串行和并行步骤的plan"""
        plan: Plan = Plan(
            goal="Test goal",
            steps={
                1: PlanStep(id=1, description="Step 1", depends_on=[], status="pending", result=None, sub_agent_task_id=None),
                2: PlanStep(id=2, description="Step 2", depends_on=[], status="pending", result=None, sub_agent_task_id=None),
                3: PlanStep(id=3, description="Step 3", depends_on=[], status="pending", result=None, sub_agent_task_id=None),
                4: PlanStep(id=4, description="Step 4", depends_on=[], status="pending", result=None, sub_agent_task_id=None),
                5: PlanStep(id=5, description="Step 5", depends_on=[], status="pending", result=None, sub_agent_task_id=None),
            },
            execution_order=[1, [2, 3, 4], 5],
            current_index=0,
            status="planning",
        )
        
        error = validate_plan(plan)
        assert error is None
    
    def test_invalid_plan_missing_step(self):
        """验证缺少step的plan"""
        plan: Plan = Plan(
            goal="Test goal",
            steps={
                1: PlanStep(id=1, description="Step 1", depends_on=[], status="pending", result=None, sub_agent_task_id=None),
            },
            execution_order=[1, 2],  # Step 2 不存在
            current_index=0,
            status="planning",
        )
        
        error = validate_plan(plan)
        assert error is not None
        assert "Step ID 2" in error
    
    def test_invalid_plan_id_mismatch(self):
        """验证step ID不匹配的plan"""
        plan: Plan = Plan(
            goal="Test goal",
            steps={
                1: PlanStep(id=2, description="Step 2", depends_on=[], status="pending", result=None, sub_agent_task_id=None),  # ID不匹配
            },
            execution_order=[1],
            current_index=0,
            status="planning",
        )
        
        error = validate_plan(plan)
        assert error is not None
        assert "ID mismatch" in error
    
    def test_invalid_plan_nonexistent_dependency(self):
        """验证依赖不存在step的plan"""
        plan: Plan = Plan(
            goal="Test goal",
            steps={
                1: PlanStep(id=1, description="Step 1", depends_on=[99], status="pending", result=None, sub_agent_task_id=None),
            },
            execution_order=[1],
            current_index=0,
            status="planning",
        )
        
        error = validate_plan(plan)
        assert error is not None
        assert "depends on non-existent step" in error
    
    def test_invalid_plan_wrong_item_type(self):
        """验证execution_order包含错误类型的plan"""
        plan: Plan = Plan(
            goal="Test goal",
            steps={
                1: PlanStep(id=1, description="Step 1", depends_on=[], status="pending", result=None, sub_agent_task_id=None),
            },
            execution_order=[1, "invalid"],  # 字符串类型无效
            current_index=0,
            status="planning",
        )
        
        error = validate_plan(plan)
        assert error is not None
        assert "Invalid execution_order item type" in error


class TestExtractAllStepIds:
    """提取step_id测试"""
    
    def test_extract_serial_steps(self):
        """提取纯串行步骤"""
        execution_order = [1, 2, 3]
        ids = extract_all_step_ids(execution_order)
        assert ids == [1, 2, 3]
    
    def test_extract_parallel_steps(self):
        """提取并行步骤"""
        execution_order = [[1, 2, 3]]
        ids = extract_all_step_ids(execution_order)
        assert ids == [1, 2, 3]
    
    def test_extract_mixed_steps(self):
        """提取混合步骤"""
        execution_order = [1, [2, 3, 4], 5]
        ids = extract_all_step_ids(execution_order)
        assert ids == [1, 2, 3, 4, 5]
    
    def test_extract_empty(self):
        """提取空列表"""
        execution_order = []
        ids = extract_all_step_ids(execution_order)
        assert ids == []
