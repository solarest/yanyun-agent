"""应用层 - Ping DTO 定义

DTO (Data Transfer Object) 用于层间数据传输
"""
from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class PingRequest(BaseModel):
    """Ping 请求 DTO"""
    message: Optional[str] = "ping"


class PingResponse(BaseModel):
    """Ping 响应 DTO"""
    status: str
    timestamp: datetime
    message: str
    server: str = "ddd-python-backend"
