"""应用层 - Team DTO"""

from typing import Optional

from pydantic import BaseModel, Field


class CreateTeamDTO(BaseModel):
    """创建 Team 请求"""
    name: str = Field(..., min_length=1, max_length=100, description="团队名称")
    description: str = Field(default="", description="团队描述")
    leader_id: str = Field(..., description="Leader Agent ID")
    member_ids: list[str] = Field(default_factory=list, description="Member Agent IDs")


class UpdateTeamDTO(BaseModel):
    """更新 Team 请求 (PATCH 语义)"""
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = None
    leader_id: Optional[str] = None
    member_ids: Optional[list[str]] = None


class ExecuteTeamDTO(BaseModel):
    """执行 Team 目标请求"""
    goal: str = Field(..., min_length=1, description="团队执行目标")
    model: Optional[str] = Field(default=None, description="LLM 模型")
    max_turns: int = Field(default=100, ge=1, le=500, description="最大轮次")
    workspace: str = Field(default="/tmp/team-workspace", description="工作目录")


class TeamMemberDTO(BaseModel):
    """团队成员响应"""
    id: str
    agent_id: str
    agent_name: str = ""
    role: str
    status: str
    joined_at: str


class TeamResponseDTO(BaseModel):
    """Team 响应"""
    id: str
    name: str
    description: str
    leader_id: str
    goal: str = ""
    status: str
    config: dict = {}
    member_count: int = 0
    created_at: str
    updated_at: Optional[str] = None


class TeamDetailDTO(TeamResponseDTO):
    """Team 详情响应（含成员列表）"""
    members: list[TeamMemberDTO] = []


class TeamListResponseDTO(BaseModel):
    """Team 列表响应"""
    teams: list[TeamResponseDTO]
    total: int
    page: int
    page_size: int


class ExecuteTeamResponseDTO(BaseModel):
    """执行 Team 响应"""
    team_id: str
    execution_id: str
    workspace: str = "/tmp/team-workspace"
    status: str = "started"
    message: str = "Team execution started"
