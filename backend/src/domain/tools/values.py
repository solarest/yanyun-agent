"""工具子域 - 工具执行结果与策略（值对象）"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
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


@dataclass(frozen=True)
class ToolPolicy:
    """工具执行策略（值对象）

    定义单个工具的执行约束。作为 RegisteredTool 的不可变属性。
    """

    timeout_ms: int = 30000
    """执行超时时间（毫秒），默认 30 秒"""

    max_calls_per_minute: int = 60
    """每分钟最大调用次数"""

    sandboxed: bool = False
    """是否需要沙箱隔离执行"""

    allowed_paths: tuple[str, ...] = ()
    """允许访问的文件路径前缀（仅 file 类工具使用）"""
