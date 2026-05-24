"""领域层 - SkillDef 技能定义实体"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class SkillStep:
    """技能步骤定义"""
    name: str
    description: str
    tool_name: Optional[str] = None
    """使用的工具（如为复合步骤可为空）"""


@dataclass
class SkillDef:
    """技能定义领域实体

    预定义的复杂任务执行流程，由多个步骤组成。
    支持两种内容模式：
    - 结构化模式：通过 steps + trigger_keywords 定义
    - 原文模式：通过 content 存储完整 SKILL.md 内容
    """

    name: str
    """技能名称，如 "code_review", "debug_assistant" """

    description: str
    """技能功能描述"""

    steps: list[SkillStep] = field(default_factory=list)
    """执行步骤列表"""

    trigger_keywords: list[str] = field(default_factory=list)
    """触发关键词，用于 LLM 识别何时使用该技能"""

    category: str = "general"
    """技能分类"""

    # 持久化字段
    id: str = ""
    """主键 ID"""

    content: str = ""
    """Skill 完整 Markdown 内容（原始 SKILL.md 内容存储）"""

    file_path: str = ""
    """磁盘存储路径（ZIP 解压后的目录路径）"""

    enabled: bool = True
    """是否启用"""

    created_at: datetime = field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None

    def to_prompt_section(self) -> str:
        """生成为 Prompt 中的技能描述段落

        如果有 content（完整 SKILL.md 内容），优先使用 content；
        否则使用结构化的 steps 生成摘要。
        """
        if self.content:
            return self.content

        parts = [
            f"### {self.name}",
            self.description,
        ]

        if self.trigger_keywords:
            parts.append(f"\n**Triggers:** {', '.join(self.trigger_keywords)}")

        if self.steps:
            parts.append("\n**Steps:**")
            for i, step in enumerate(self.steps, 1):
                tool_info = f" (using `{step.tool_name}`)" if step.tool_name else ""
                parts.append(
                    f"{i}. **{step.name}**{tool_info}: {step.description}")

        return "\n".join(parts)

    def toggle_enabled(self) -> None:
        """切换启用状态"""
        self.enabled = not self.enabled
        self.updated_at = datetime.now()
