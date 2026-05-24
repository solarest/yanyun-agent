"""领域层 - 工具执行结果与上下文

ToolResult: 所有工具执行后统一返回此结构
ToolContext: 传递给工具的运行时上下文信息
"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ToolResult:
    """工具执行结果

    所有工具执行后统一返回此结构。
    """

    output: str
    """文本输出（将作为 tool message content 返回给 LLM）"""

    success: bool = True
    """是否执行成功"""

    error: Optional[str] = None
    """错误信息（失败时填写）"""

    metadata: dict[str, Any] = field(default_factory=dict)
    """附加元数据（如 token 消耗、执行耗时等，不返回给 LLM）"""


@dataclass
class ToolContext:
    """工具执行上下文

    传递给工具的运行时上下文信息，工具可按需使用。
    """

    task_id: str
    """当前任务 ID"""

    workspace: str = ""
    """工作目录路径"""

    user_id: Optional[str] = None
    """当前用户 ID"""

    agent_id: Optional[str] = None
    """当前 Agent ID"""

    extra: dict[str, Any] = field(default_factory=dict)
    """扩展上下文（由具体工具自行解析）"""
