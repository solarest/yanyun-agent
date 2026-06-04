"""应用层 - Agent DTO"""

from pydantic import BaseModel, Field, field_validator, model_validator
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
    description: str = Field(
        default="",
        max_length=500,
        description="Agent 功能描述",
        examples=["帮助你管理日程和提醒的智能助手"],
    )
    vibes: list[str] = Field(
        default_factory=list,
        description="性格特征标签（1-3 个）",
    )
    identity_md: Optional[str] = Field(
        default=None,
        max_length=50000,
        description="IDENTITY.md 内容",
    )
    soul_md: Optional[str] = Field(
        default=None,
        max_length=50000,
        description="SOUL.md 内容",
    )
    agents_md: Optional[str] = Field(
        default=None,
        max_length=50000,
        description="AGENTS.md 内容",
    )
    bootstrap_md: Optional[str] = Field(
        default=None,
        max_length=50000,
        description="BOOTSTRAP.md 内容",
    )
    memory_md: Optional[str] = Field(
        default=None,
        max_length=50000,
        description="MEMORY.md 内容",
    )
    tools_md: Optional[str] = Field(
        default=None,
        max_length=50000,
        description="TOOLS.md 内容",
    )
    user_md: Optional[str] = Field(
        default=None,
        max_length=50000,
        description="USER.md 内容",
    )

    @field_validator("vibes")
    @classmethod
    def validate_vibes_count(cls, v: list[str]) -> list[str]:
        if len(v) > 3:
            raise ValueError("vibes 最多只能选择 3 个")
        return v


class UpdateAgentDTO(BaseModel):
    """更新 Agent 请求 DTO（PATCH 语义，所有字段可选）"""

    name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Agent 名称",
    )
    description: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Agent 功能描述",
    )
    vibes: Optional[list[str]] = Field(
        default=None,
        description="性格特征标签（1-3 个）",
    )
    identity_md: Optional[str] = Field(
        default=None,
        max_length=50000,
        description="IDENTITY.md 内容",
    )
    soul_md: Optional[str] = Field(
        default=None,
        max_length=50000,
        description="SOUL.md 内容",
    )
    agents_md: Optional[str] = Field(
        default=None,
        max_length=50000,
        description="AGENTS.md 内容",
    )
    bootstrap_md: Optional[str] = Field(
        default=None,
        max_length=50000,
        description="BOOTSTRAP.md 内容",
    )
    memory_md: Optional[str] = Field(
        default=None,
        max_length=50000,
        description="MEMORY.md 内容",
    )
    tools_md: Optional[str] = Field(
        default=None,
        max_length=50000,
        description="TOOLS.md 内容",
    )
    user_md: Optional[str] = Field(
        default=None,
        max_length=50000,
        description="USER.md 内容",
    )

    @field_validator("vibes")
    @classmethod
    def validate_vibes_count(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is not None and len(v) > 3:
            raise ValueError("vibes 最多只能选择 3 个")
        return v


class UpdateAgentConfigDTO(BaseModel):
    """更新 Agent 配置文件 DTO（至少需要一个字段非 None）"""

    identity_md: Optional[str] = Field(
        default=None,
        max_length=50000,
        description="IDENTITY.md 内容",
    )
    soul_md: Optional[str] = Field(
        default=None,
        max_length=50000,
        description="SOUL.md 内容",
    )
    agents_md: Optional[str] = Field(
        default=None,
        max_length=50000,
        description="AGENTS.md 内容",
    )
    bootstrap_md: Optional[str] = Field(
        default=None,
        max_length=50000,
        description="BOOTSTRAP.md 内容",
    )
    memory_md: Optional[str] = Field(
        default=None,
        max_length=50000,
        description="MEMORY.md 内容",
    )
    tools_md: Optional[str] = Field(
        default=None,
        max_length=50000,
        description="TOOLS.md 内容",
    )
    user_md: Optional[str] = Field(
        default=None,
        max_length=50000,
        description="USER.md 内容",
    )

    @model_validator(mode="after")
    def validate_at_least_one_field(self) -> "UpdateAgentConfigDTO":
        fields = [
            self.identity_md,
            self.soul_md,
            self.agents_md,
            self.bootstrap_md,
            self.memory_md,
            self.tools_md,
            self.user_md,
        ]
        if all(f is None for f in fields):
            raise ValueError("至少需要提供一个配置文件字段")
        return self


class AgentResponseDTO(BaseModel):
    """Agent 响应 DTO"""

    id: str
    name: str
    description: str
    vibes: list[str]
    identity_md: str
    soul_md: str
    agents_md: str
    bootstrap_md: str
    memory_md: str
    tools_md: str
    user_md: str
    config_version: int
    created_at: str
    updated_at: Optional[str] = None


class AgentConfigResponseDTO(BaseModel):
    """Agent 配置文件响应 DTO"""

    identity_md: str
    soul_md: str
    agents_md: str
    bootstrap_md: str
    memory_md: str
    tools_md: str
    user_md: str
    config_version: int


class AgentListResponseDTO(BaseModel):
    """Agent 列表响应 DTO"""

    data: list[AgentResponseDTO]
    total: int
