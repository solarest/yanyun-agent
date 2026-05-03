"""领域层 - ToolDef 工具定义实体"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ToolParameter:
    """工具参数定义"""
    name: str
    type: str  # "string", "number", "boolean", "object", "array"
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
    """工具名称，如 "web_search", "read_file" """

    description: str
    """工具功能描述，用于 LLM 理解何时使用"""

    parameters: list[ToolParameter] = field(default_factory=list)
    """参数列表"""

    returns: str = ""
    """返回值描述"""

    # 元数据
    category: str = "general"
    """工具分类：web_search / file / clarify / plan / mcp / custom """

    def to_prompt_section(self) -> str:
        """生成为 Prompt 中的工具描述段落（XML 格式）

        使用 XML 格式便于 LLM 解析和处理工具定义。

        Returns:
            XML 格式的工具描述文本
        """
        parts = [f'<tool name="{self.name}">']
        parts.append(f"  <description>{self.description}</description>")

        if self.parameters:
            parts.append("  <parameters>")
            for p in self.parameters:
                req = "true" if p.required else "false"
                enum_str = ""
                if p.enum:
                    enum_values = ", ".join(str(v) for v in p.enum)
                    enum_str = f'\n          <enum>{enum_values}</enum>'
                parts.append(
                    f'    <param name="{p.name}" type="{p.type}" required="{req}">{p.description}{enum_str}</param>'
                )
            parts.append("  </parameters>")

        if self.returns:
            parts.append(f"  <returns>{self.returns}</returns>")

        parts.append("</tool>")

        return "\n".join(parts)
