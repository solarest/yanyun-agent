"""应用层 - Skill DTO 定义"""

from typing import Optional

from pydantic import BaseModel, Field


class SkillStepDTO(BaseModel):
    """Skill 步骤 DTO"""

    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1, max_length=500)
    tool_name: Optional[str] = Field(default=None, max_length=100)


class SkillResponseDTO(BaseModel):
    """Skill 响应 DTO"""

    id: str
    name: str
    description: str
    content: str
    file_path: str = ""
    trigger_keywords: list[str]
    steps: list[SkillStepDTO]
    category: str
    enabled: bool
    created_at: str
    updated_at: Optional[str] = None


class SkillListResponseDTO(BaseModel):
    """Skill 列表响应 DTO"""

    data: list[SkillResponseDTO]
    total: int
