"""领域层 - 工具定义实体

ToolDef 和 ToolParameter 是 Tools 模块与 Prompt Builder 的共享契约。
Prompt Builder Layer 5 使用 ToolDef.to_prompt_section() 将工具描述渲染到系统提示词中。
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ToolParameter:
    """工具参数定义"""

    name: str
    type: str  # "string", "integer", "number", "boolean", "object", "array"
    description: str
    required: bool = True
    enum: Optional[list] = None
    """枚举值（可选）"""


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

        Returns:
            工具名称标记文本，如 "- web_search"
        """
        return f"- {self.name}"

    def to_llm_schema(self) -> dict:
        """生成 LLM API 调用时的工具 Schema（详细形式）

        用于 bind_tools() 参数，包含完整的工具描述和参数定义。
        符合 OpenAI Chat Completions API 的 tools 参数格式。

        Returns:
            工具 Schema 字典，格式为:
            {
                "type": "function",
                "function": {
                    "name": "tool_name",
                    "description": "tool description",
                    "parameters": {
                        "type": "object",
                        "properties": {...},
                        "required": [...]
                    }
                }
            }
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
