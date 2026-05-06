"""领域层 - SKILL.md 解析器

从 SKILL.md 内容中提取 name 和 description。
解析规则：
  - name: 第一个 H1 标题（# 开头的行）
  - description: H1 之后的第一个非空段落
"""

import re


def parse_skill_md(content: str) -> tuple[str, str]:
    """解析 SKILL.md 内容，返回 (name, description)。

    Args:
        content: SKILL.md 的原始文本内容

    Returns:
        (name, description) 元组，未找到时返回空字符串
    """
    name = ""
    description = ""

    lines = content.split("\n")
    h1_found = False

    for i, line in enumerate(lines):
        stripped = line.strip()

        # 寻找第一个 H1 标题
        if not h1_found:
            match = re.match(r"^#\s+(.+)$", stripped)
            if match:
                name = match.group(1).strip()
                h1_found = True
            continue

        # H1 之后，跳过空行，取第一个非标题非空段落
        if not stripped:
            continue
        if stripped.startswith("#"):
            break
        description = stripped
        break

    return name, description
