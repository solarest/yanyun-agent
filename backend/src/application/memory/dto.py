"""应用层 - Memory DTO"""

from typing import Optional

from pydantic import BaseModel, Field


class MemoryCreateDTO(BaseModel):
    """创建记忆请求 DTO"""

    content: str = Field(..., min_length=1, max_length=10000)
    category: str = Field(default="general")
    tags: list[str] = Field(default_factory=list)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    source_session_id: str = Field(default="")


class MemoryUpdateDTO(BaseModel):
    """更新记忆请求 DTO"""

    content: Optional[str] = Field(default=None, max_length=10000)
    category: Optional[str] = None
    tags: Optional[list[str]] = None
    importance: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class MemoryResponseDTO(BaseModel):
    """记忆响应 DTO"""

    id: str
    agent_id: str
    content: str
    category: str
    tags: list[str]
    importance: float
    source_session_id: str
    access_count: int
    last_accessed_at: Optional[str] = None
    created_at: str
    updated_at: Optional[str] = None


class MemoryListResponseDTO(BaseModel):
    """记忆列表响应 DTO"""

    data: list[MemoryResponseDTO]
    total: int


class MemorySearchRequestDTO(BaseModel):
    """记忆搜索请求 DTO"""

    query: str = Field(default="", max_length=500)
    category: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    min_importance: float = Field(default=0.0, ge=0.0, le=1.0)
    limit: int = Field(default=10, ge=1, le=50)


class MemorySearchResponseDTO(BaseModel):
    """记忆搜索结果 DTO"""

    id: str
    agent_id: str
    content: str
    category: str
    tags: list[str]
    importance: float
    score: float
    created_at: str
