"""领域层 - Tool 聚合

统一 re-export，外部使用：
    from src.domain.tool import ToolResult, ToolContext, ToolDef, ...

按聚合分包，避免根目录平铺过多 tool 相关文件。
"""

from src.domain.tool.entities.call import ToolCall, ToolCallState
from src.domain.tool.entities.context import ToolContext, ToolResult
from src.domain.tool.entities.definition import ToolDef, ToolParameter
from src.domain.tool.entities.policy import ToolPolicy
from src.domain.tool.entities.registered import RegisteredTool, ToolFunction

__all__ = [
    "RegisteredTool",
    "ToolCall",
    "ToolCallState",
    "ToolContext",
    "ToolDef",
    "ToolFunction",
    "ToolParameter",
    "ToolPolicy",
    "ToolResult",
]
