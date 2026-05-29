"""领域层 - 工具执行策略（值对象）

ToolPolicy 定义单个工具的执行约束，是 RegisteredTool 的不可变属性。
"""

from dataclasses import dataclass


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
