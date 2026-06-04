"""应用层 - LLM 配置 DTO"""

from pydantic import BaseModel, Field


class LLMProviderInfoDTO(BaseModel):
    """LLM 提供商信息 DTO"""

    name: str = Field(..., description="提供商名称")
    available_models: list[str] = Field(default_factory=list, description="可用模型列表")
