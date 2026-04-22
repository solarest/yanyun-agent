"""应用层 - LLM 配置 DTO"""

from pydantic import BaseModel, Field
from typing import Optional


class LLMConfigDTO(BaseModel):
    """LLM 配置请求 DTO"""

    provider: str = Field(..., description="LLM 提供商名称")
    model: str = Field(..., description="模型名称")
    temperature: float = Field(default=0.7, ge=0, le=2, description="温度参数")
    max_tokens: Optional[int] = Field(default=None, ge=1, description="最大生成 token 数")
    timeout: int = Field(default=60, ge=1, description="超时时间（秒）")
    max_retries: int = Field(default=3, ge=0, description="最大重试次数")
    extra: dict = Field(default_factory=dict, description="额外参数")


class LLMUsageResponseDTO(BaseModel):
    """LLM 使用量响应 DTO"""

    total_tokens: int = Field(..., description="总 token 数")
    prompt_tokens: int = Field(..., description="输入 token 数")
    completion_tokens: int = Field(..., description="输出 token 数")
    total_cost: float = Field(..., description="总成本（美元）")
    model: str = Field(..., description="模型名称")


class LLMProviderInfoDTO(BaseModel):
    """LLM 提供商信息 DTO"""

    name: str = Field(..., description="提供商名称")
    available_models: list[str] = Field(default_factory=list, description="可用模型列表")
