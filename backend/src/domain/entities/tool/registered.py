"""领域层 - 已注册工具实体

将工具函数、元数据定义、执行策略绑定在一起。
由 @tool 装饰器自动创建，或由适配器手动构建。
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from src.domain.entities.tool.context import ToolResult
from src.domain.entities.tool.definition import ToolDef, ToolParameter
from src.domain.entities.tool.policy import ToolPolicy

# 工具函数类型：接收 Dict 参数和可选 Context，返回 ToolResult
ToolFunction = Callable[..., Coroutine[Any, Any, ToolResult]]


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

    policy: ToolPolicy = field(default_factory=ToolPolicy)
    """执行策略"""

    def to_tool_def(self) -> ToolDef:
        """转换为 ToolDef 实体（供 Prompt Builder 使用）

        Returns:
            与 1.2_prompt-builder.md 定义的 ToolDef 结构对齐
        """
        return ToolDef(
            name=self.name,
            description=self.description,
            parameters=self.parameters,
            returns=self.returns,
            category=self.category,
        )
