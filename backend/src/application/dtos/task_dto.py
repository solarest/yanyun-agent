"""应用层 - 任务 DTO"""
from pydantic import BaseModel, Field
from typing import Any, Dict, Optional


class CreateTaskDTO(BaseModel):
    """创建任务请求 DTO"""
    message: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="任务描述",
        examples=["Create a hello world TypeScript app"],
    )
    workspace: str = Field(
        ...,
        min_length=1,
        description="工作目录路径",
        examples=["/tmp/test-workspace"],
    )
    max_turns: Optional[int] = Field(
        default=100,
        ge=1,
        le=500,
        description="最大执行轮次",
    )
    model: Optional[str] = Field(
        default="gpt-4",
        description="使用的模型",
    )


class TaskResponseDTO(BaseModel):
    """任务响应 DTO"""
    id: str
    message: str
    workspace: str
    status: str
    model: str
    current_turn: int
    max_turns: int
    result: Optional[str] = None
    error: Optional[str] = None
    cost: Dict[str, Any] = {}
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class TaskListResponseDTO(BaseModel):
    """任务列表响应 DTO"""
    data: list[TaskResponseDTO]
    total: int
