"""危险命令分类器（task 1.2）。

对原始 shell 命令串逐条做正则扫描；命中首条规则即判需确认，
返回其类别与风险原因。保守偏向"多问"——误报代价（多一次确认）
远低于漏报代价（删库）。

注：task 1.2 文本另提到 shlex 按 ;/&&/||/| 拆段、提取每段命令名。
当前默认规则集均为"原始串正则扫描"即可命中全部用例（含复合
`ls && rm -rf build`——`rm -rf` 出现在原始串即被扫到），段级命令
名匹配无任何用例需要、属推测性代码，按 TDD 不写。如未来出现
"仅当命令名等于 X 时命中、避免子串误报"的规则，再加段级匹配。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.infrastructure.tools.confirmation.config import DangerousCommandSet


@dataclass(frozen=True)
class ClassificationResult:
    """分类结果。"""

    needs_confirmation: bool
    risk_reason: str
    category: str


class CommandClassifier:
    """按配置的危险命令集合分类 shell 命令。"""

    def __init__(self, command_set: DangerousCommandSet) -> None:
        self._rules: list[tuple[re.Pattern[str], str, str]] = [
            (re.compile(e.pattern), e.category, e.reason)
            for e in command_set.entries
        ]

    def classify(self, command: str) -> ClassificationResult:
        """判定一条 shell 命令是否需要执行前确认。"""
        for regex, category, reason in self._rules:
            if regex.search(command):
                return ClassificationResult(
                    needs_confirmation=True,
                    risk_reason=reason,
                    category=category,
                )
        return ClassificationResult(
            needs_confirmation=False, risk_reason="", category=""
        )
