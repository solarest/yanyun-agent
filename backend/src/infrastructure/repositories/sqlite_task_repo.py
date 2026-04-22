"""基础设施层 - TaskRepository SQLite 实现"""
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.task import Task, TaskConfig, CostTracker, TaskStatus
from src.domain.repositories.task_repository import ITaskRepository
from src.infrastructure.database.models.agent_model import TaskModel


class SQLiteTaskRepository(ITaskRepository):
    """SQLite 任务仓储实现"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_by_id(self, task_id: str) -> Optional[Task]:
        """根据 ID 获取任务"""
        result = await self.session.execute(
            select(TaskModel).where(TaskModel.id == task_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return None
        return self._to_entity(model)
    
    async def add(self, task: Task) -> Task:
        """添加任务"""
        model = self._to_model(task)
        self.session.add(model)
        await self.session.commit()
        await self.session.refresh(model)
        return self._to_entity(model)
    
    async def update(self, task: Task) -> Task:
        """更新任务"""
        result = await self.session.execute(
            select(TaskModel).where(TaskModel.id == task.id)
        )
        model = result.scalar_one_or_none()
        if not model:
            raise ValueError(f"Task {task.id} not found")
        
        # 更新字段
        model.message = task.message
        model.workspace = task.workspace
        model.status = task.status.value
        model.model = task.model
        model.config = {
            "max_turns": task.config.max_turns,
            "temperature": task.config.temperature,
        }
        model.current_turn = task.current_turn
        model.max_turns = task.max_turns
        model.result = task.result
        model.error = task.error
        model.cost = task.cost.to_dict()
        model.started_at = task.started_at
        model.completed_at = task.completed_at
        
        await self.session.commit()
        await self.session.refresh(model)
        return self._to_entity(model)
    
    async def remove(self, task_id: str) -> bool:
        """删除任务"""
        result = await self.session.execute(
            select(TaskModel).where(TaskModel.id == task_id)
        )
        model = result.scalar_one_or_none()
        if not model:
            return False
        
        await self.session.delete(model)
        await self.session.commit()
        return True
    
    async def list_all(self, limit: int = 100, offset: int = 0) -> List[Task]:
        """获取任务列表"""
        result = await self.session.execute(
            select(TaskModel)
            .order_by(TaskModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        models = result.scalars().all()
        return [self._to_entity(m) for m in models]
    
    def _to_entity(self, model: TaskModel) -> Task:
        """数据库模型转领域实体"""
        return Task(
            id=model.id,
            message=model.message,
            workspace=model.workspace,
            status=TaskStatus(model.status),
            model=model.model,
            config=TaskConfig(
                max_turns=model.config.get("max_turns", 100),
                temperature=model.config.get("temperature", 0.7),
            ),
            current_turn=model.current_turn,
            max_turns=model.max_turns,
            result=model.result,
            error=model.error,
            cost=CostTracker(**model.cost) if model.cost else CostTracker(),
            created_at=model.created_at,
            started_at=model.started_at,
            completed_at=model.completed_at,
        )
    
    def _to_model(self, entity: Task) -> TaskModel:
        """领域实体转数据库模型"""
        return TaskModel(
            id=entity.id,
            message=entity.message,
            workspace=entity.workspace,
            status=entity.status.value,
            model=entity.model,
            config={
                "max_turns": entity.config.max_turns,
                "temperature": entity.config.temperature,
            },
            current_turn=entity.current_turn,
            max_turns=entity.max_turns,
            result=entity.result,
            error=entity.error,
            cost=entity.cost.to_dict(),
            created_at=entity.created_at,
            started_at=entity.started_at,
            completed_at=entity.completed_at,
        )
