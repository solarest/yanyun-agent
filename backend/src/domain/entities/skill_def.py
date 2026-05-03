"""领域层 - SkillDef 技能定义实体"""

from dataclasses import dataclass, field
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
    由 Skills 模块提供具体实现，此处只定义结构。
    """

    name: str
    """技能名称，如 "code_review", "debug_assistant" """

    description: str
    """技能功能描述"""

    steps: list[SkillStep] = field(default_factory=list)
    """执行步骤列表"""

    trigger_keywords: list[str] = field(default_factory=list)
    """触发关键词，用于 LLM 识别何时使用该技能"""

    # 元数据
    category: str = "general"
    """技能分类"""

    def to_prompt_section(self) -> str:
        """生成为 Prompt 中的技能描述段落"""
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
