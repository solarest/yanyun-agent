"""领域层 - Prompt 组装结果值对象"""

from dataclasses import dataclass, field


@dataclass
class PromptAssemblyResult:
    """Prompt 组装结果值对象

    PromptAssembleService.assemble() 的返回值。
    system_message 作为 LLM API 的 system role content，
    对话历史由 PromptContextInterface 独立管理。
    """

    system_message: str
    """11 层拼接后的系统消息内容，直接用于 {"role": "system", "content": ...}"""

    static_prefix_tokens: int = 0
    """Layer 1-3 的 token 数（用于 Prompt Cache 命中标记）"""

    total_token_estimate: int = 0
    """系统消息的总 token 预估（不含对话历史）"""

    layers: dict = field(default_factory=dict)
    """各层元信息，用于调试和可观测性"""
