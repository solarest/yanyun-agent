"""领域层 - Tool 聚合

统一 re-export，外部使用：
    from src.domain.entities.tool import ToolResult, ToolContext, ToolDef, ...

按聚合分包，避免 entities/ 根目录平铺过多 tool 相关文件。
"""

from src.domain.entities.tool.call import ToolCall, ToolCallState
from src.domain.entities.tool.context import ToolContext, ToolResult
from src.domain.entities.tool.definition import ToolDef, ToolParameter
from src.domain.entities.tool.policy import ToolPolicy
from src.domain.entities.tool.registered import RegisteredTool, ToolFunction

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
