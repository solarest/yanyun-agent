"""应用层 - Session DTO"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CreateSessionDTO(BaseModel):
    """创建会话请求"""

    title: Optional[str] = Field(default=None, max_length=200)


class UpdateSessionDTO(BaseModel):
    """更新会话请求"""

    title: Optional[str] = Field(default=None, max_length=200)
    status: Optional[str] = Field(default=None)


class SendMessageDTO(BaseModel):
    """发送消息请求"""

    content: str = Field(..., min_length=1,
                         max_length=50000, description="消息内容")
    model: Optional[str] = Field(default=None, description="使用的模型")
    max_turns: Optional[int] = Field(
        default=100, ge=1, le=500, description="最大轮次")
    workspace: Optional[str] = Field(
        default="/tmp/agent-workspace", description="工作目录")
    skill_ids: List[str] = Field(
        default_factory=list, description="选中的 Skill ID 列表")


class SessionResponseDTO(BaseModel):
    """会话响应"""

    id: str
    agent_id: str
    title: str
    status: str
    message_count: int
    last_message_preview: str
    created_at: str
    updated_at: Optional[str] = None


class SessionMessageResponseDTO(BaseModel):
    """会话消息响应"""

    id: str
    session_id: str
    task_id: Optional[str] = None
    role: str
    content: str
    thinking_content: str = ""
    has_thinking: bool = False
    tool_calls: List[Dict[str, Any]] = []
    tool_results: List[Dict[str, Any]] = []
    status: str
    error: Optional[str] = None
    cost: Dict[str, Any] = {}
    created_at: str


class SessionDetailResponseDTO(BaseModel):
    """会话详情响应（含消息列表）"""

    session: SessionResponseDTO
    messages: List[SessionMessageResponseDTO]


class SendMessageResponseDTO(BaseModel):
    """发送消息响应"""

    user_message: SessionMessageResponseDTO
    task_id: str


class SessionListResponseDTO(BaseModel):
    """会话列表响应"""

    data: List[SessionResponseDTO]
    total: int
