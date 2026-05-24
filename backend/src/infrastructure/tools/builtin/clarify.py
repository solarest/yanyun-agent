"""基础设施层 - 澄清提问工具

当任务需求不明确或存在歧义时，向用户发起澄清提问。
"""

from typing import Optional

from src.domain.tool import ToolContext, ToolResult
from src.infrastructure.tools.decorator import tool


@tool(
    name="clarify",
    description="当任务需求不明确或存在歧义时，向用户发起澄清提问。提供选项可降低用户回答负担。",
    category="clarify",
    returns="标记为等待用户回复的特殊响应",
    timeout_ms=5000,
)
async def clarify(
    question: str,
    options: Optional[list[str]] = None,
    context: Optional[ToolContext] = None,
) -> ToolResult:
    """澄清提问工具

    Args:
        question: 要向用户提出的问题
        options: 可选的选项列表，提供给用户选择
    """
    if not question.strip():
        return ToolResult(
            output="Error: question cannot be empty",
            success=False,
            error="invalid_input",
        )

    output_parts = [f"**Question**: {question}"]
    if options:
        output_parts.append("\n**Options**:")
        for i, opt in enumerate(options, 1):
            output_parts.append(f"  {i}. {opt}")

    return ToolResult(
        output="\n".join(output_parts),
        metadata={
            "type": "clarify",
            "question": question,
            "options": options or [],
            "awaiting_user_input": True,
        },
    )
