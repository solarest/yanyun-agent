"""工具子域 - 工具定义实体"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, Optional

from src.domain.entities.base import Entity


# ── ToolParameter ────────────────────────────────────────────

@dataclass
class ToolParameter:
    """工具参数定义"""

    name: str
    type: str  # "string", "integer", "number", "boolean", "object", "array"
    description: str
    required: bool = True
    enum: Optional[list] = None
    """枚举值（可选）"""


# ── ToolDef ──────────────────────────────────────────────────

@dataclass
class ToolDef:
    """工具定义领域实体

    描述一个可被 Agent 调用的工具，包含名称、描述、参数 Schema。
    由 Tools Hub 模块提供具体实现，此处只定义结构。
    """

    name: str
    """工具名称，如 "web_search", "file_read" """

    description: str
    """工具功能描述，用于 LLM 理解何时使用"""

    parameters: list[ToolParameter] = field(default_factory=list)
    """参数列表"""

    returns: str = ""
    """返回值描述"""

    category: str = "general"
    """工具分类：web_search / file / clarify / plan / mcp / custom"""

    def to_prompt_section(self) -> str:
        """生成 System Prompt 中的工具名称标记（简短形式）

        用于 Layer 5 Available Tools 部分，只标记工具名称列表。
        工具的详细信息通过 to_llm_schema() 生成并传递给 bind_tools()。
        """
        return f"- {self.name}"

    def to_llm_schema(self) -> dict:
        """生成 LLM API 调用时的工具 Schema（详细形式）

        用于 bind_tools() 参数，包含完整的工具描述和参数定义。
        符合 OpenAI Chat Completions API 的 tools 参数格式。
        """
        properties = {}
        required_params = []

        for param in self.parameters:
            prop_def = {
                "type": param.type,
                "description": param.description,
            }
            if param.enum:
                prop_def["enum"] = param.enum
            properties[param.name] = prop_def

            if param.required:
                required_params.append(param.name)

        function_def = {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": properties,
            },
        }

        if required_params:
            function_def["parameters"]["required"] = required_params

        return {
            "type": "function",
            "function": function_def,
        }


# ── RegisteredTool ───────────────────────────────────────────

# 工具函数类型：接收 Dict 参数和可选 Context，返回 ToolResult
ToolFunction = Callable[..., Coroutine[Any, Any, Any]]


@dataclass
class RegisteredTool:
    """已注册的工具实体

    将工具函数、元数据定义、执行策略绑定在一起。
    由 @tool 装饰器自动创建，或由适配器手动构建。
    """

    name: str
    """工具唯一名称"""

    description: str
    """功能描述（用于 LLM 理解何时调用）"""

    func: ToolFunction
    """实际执行函数"""

    parameters: list[ToolParameter] = field(default_factory=list)
    """参数定义列表"""

    returns: str = ""
    """返回值描述"""

    category: str = "general"
    """工具分类"""

    policy: Any = None
    """执行策略（ToolPolicy 实例）"""

    def to_tool_def(self) -> ToolDef:
        """转换为 ToolDef 实体（供 Prompt Builder 使用）"""
        return ToolDef(
            name=self.name,
            description=self.description,
            parameters=self.parameters,
            returns=self.returns,
            category=self.category,
        )


# ── ToolCall ─────────────────────────────────────────────────

class ToolCallState(str, Enum):
    """工具调用状态"""

    VALIDATING = "validating"
    SCHEDULED = "scheduled"
    EXECUTING = "executing"
    SUCCESS = "success"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class ToolCall(Entity):
    """工具调用实体"""

    task_id: str = ""  # 关联任务 ID
    name: str = ""  # 工具名称
    input: Dict[str, Any] = field(default_factory=dict)  # 输入参数
    state: ToolCallState = ToolCallState.VALIDATING
    result: Optional[str] = None
    error: Optional[str] = None
    error_type: Optional[str] = None  # recoverable/fatal/timeout
    duration_ms: int = 0
    created_at: datetime = field(default_factory=datetime.now)
