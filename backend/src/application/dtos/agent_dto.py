"""应用层 - Agent DTO"""

from pydantic import BaseModel, Field
from typing import Optional


class CreateAgentDTO(BaseModel):
    """创建 Agent 请求 DTO"""

    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Agent 名称（唯一）",
        examples=["Code Reviewer"],
    )
    role: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Agent 角色描述",
        examples=["资深代码审查专家"],
    )
    system_prompt_template: Optional[str] = Field(
        default=None,
        max_length=10000,
        description="系统提示词模板，为 null 时使用默认模板。支持 {name}、{role}、{workspace} 变量",
    )


class UpdateAgentDTO(BaseModel):
    """更新 Agent 请求 DTO（PATCH 语义，所有字段可选）"""

    name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Agent 名称",
    )
    role: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=500,
        description="Agent 角色描述",
    )
    system_prompt_template: Optional[str] = Field(
        default=None,
        max_length=10000,
        description="系统提示词模板",
    )


class AgentResponseDTO(BaseModel):
    """Agent 响应 DTO"""

    id: str
    name: str
    role: str
    system_prompt_template: str
    created_at: str
    updated_at: Optional[str] = None


class AgentListResponseDTO(BaseModel):
    """Agent 列表响应 DTO"""

    data: list[AgentResponseDTO]
    total: int
