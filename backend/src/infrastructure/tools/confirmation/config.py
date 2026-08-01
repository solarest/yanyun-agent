"""危险命令集合配置加载。

从 JSON 配置文件读取危险命令条目（正则 pattern + 类别 + 原因），
默认加载随包分发的 `dangerous_commands.json`，可用 `path` 指向自定义文件。
配置非硬编码，便于在不改代码的前提下调整集合。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_DEFAULT_PATH = Path(__file__).parent / "dangerous_commands.json"


@dataclass(frozen=True)
class DangerousCommandEntry:
    """单条危险命令规则。"""

    pattern: str
    """匹配命令串的正则表达式（源串，调用方自行编译）"""

    category: str
    """命令类别 / 模式名，用于会话级 allow-all 白名单建键"""

    reason: str
    """风险原因，回传给前端确认卡展示"""


@dataclass(frozen=True)
class DangerousCommandSet:
    """加载后的危险命令集合（不可变）。"""

    entries: tuple[DangerousCommandEntry, ...]


def load_dangerous_commands(path: Optional[str] = None) -> DangerousCommandSet:
    """加载危险命令集合。

    Args:
        path: 配置文件路径；为 None 时加载随包分发的默认集合。
    """
    p = Path(path) if path else _DEFAULT_PATH
    raw = json.loads(p.read_text(encoding="utf-8"))
    items = raw.get("dangerous_commands", [])
    entries = tuple(
        DangerousCommandEntry(
            pattern=str(it["pattern"]),
            category=str(it["category"]),
            reason=str(it["reason"]),
        )
        for it in items
    )
    return DangerousCommandSet(entries=entries)
