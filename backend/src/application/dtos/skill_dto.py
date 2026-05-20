"""应用层 - Skill DTO 定义"""

from typing import Optional

from pydantic import BaseModel, Field


class SkillStepDTO(BaseModel):
    """Skill 步骤 DTO"""

    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1, max_length=500)
    tool_name: Optional[str] = Field(default=None, max_length=100)


class CreateSkillDTO(BaseModel):
    """创建 Skill 请求 DTO"""

    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Skill 名称（唯一标识）",
    )
    description: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Skill 功能描述",
    )
    content: str = Field(
        default="",
        max_length=50000,
        description="Skill 完整内容（Markdown 格式）",
    )
    trigger_keywords: list[str] = Field(
        default_factory=list,
        description="触发关键词列表",
    )
    steps: list[SkillStepDTO] = Field(
        default_factory=list,
        description="执行步骤定义",
    )
    category: str = Field(
        default="general",
        max_length=50,
        description="Skill 分类",
    )


class UpdateSkillDTO(BaseModel):
    """更新 Skill 请求 DTO（PATCH 语义，所有字段可选）"""

    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = Field(
        default=None, min_length=1, max_length=1000)
    content: Optional[str] = Field(default=None, max_length=50000)
    trigger_keywords: Optional[list[str]] = None
    steps: Optional[list[SkillStepDTO]] = None
    category: Optional[str] = Field(default=None, max_length=50)


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
