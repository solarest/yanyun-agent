"""领域层 - OutputSchema 输出格式实体"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import json


@dataclass
class OutputSchema:
    """输出 Schema 领域实体

    定义 LLM 输出的 JSON Schema 格式，与领域层 DTO 对齐。
    """

    id: str
    name: str
    json_schema: dict
    description: str = ""

    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None

    def validate_schema(self) -> bool:
        """验证 JSON Schema 格式"""
        if not isinstance(self.json_schema, dict):
            return False
        return "type" in self.json_schema or "$schema" in self.json_schema

    def to_json_string(self) -> str:
        """序列化 Schema 为 JSON 字符串"""
        return json.dumps(self.json_schema, indent=2, ensure_ascii=False)

    def estimate_tokens(self) -> int:
        """预估 Schema 的 Token 数量"""
        from .prompt_template import _count_tokens
        return _count_tokens(self.to_json_string())
