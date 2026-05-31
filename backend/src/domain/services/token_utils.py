"""领域层 - Token 估算工具

提供纯函数用于 Token 估算、模型上下文窗口解析、消息渲染和上下文超限错误识别。
所有函数无副作用，不依赖基础设施层。
"""

from typing import Any


# ── 模型上下文窗口注册表 ──────────────────────────────────────

# 项目策略默认值，不作为供应商规格真值
_MODEL_CONTEXT_WINDOWS: list[tuple[str, int]] = [
    ("gemini-3-pro", 2_000_000),
    ("gpt-5.5", 1_000_000),
    ("gpt-5.4", 1_000_000),
    ("claude-opus-4.7", 1_000_000),
    ("claude-opus-4.6", 1_000_000),
    ("qwen3", 1_000_000),
    ("deepseek-v4", 1_000_000),
]

_DEFAULT_CONTEXT_WINDOW = 128_000


def resolve_max_context_tokens(model_name: str) -> int:
    """根据模型名称解析最大上下文窗口 Token 数

    使用子串匹配，按注册表顺序匹配（先匹配更具体的名称）。
    未匹配到任何模型时返回默认值 128_000。

    Args:
        model_name: 模型名称（如 "gpt-4", "deepseek-v4-pro" 等）

    Returns:
        最大上下文 Token 数
    """
    model_lower = model_name.lower()
    for pattern, window in _MODEL_CONTEXT_WINDOWS:
        if pattern in model_lower:
            return window
    return _DEFAULT_CONTEXT_WINDOW


# ── Token 估算 ──────────────────────────────────────────────

def count_tokens(text: str) -> int:
    """简单 Token 计数

    估算规则：
    - 中文字符：1.5 tokens/字符
    - 其他字符：0.25 tokens/字符

    Args:
        text: 要计算的文本

    Returns:
        预估的 token 数量
    """
    chinese_chars = sum(1 for c in text if '一' <= c <= '鿿')
    other_chars = len(text) - chinese_chars
    return int(chinese_chars * 1.5 + other_chars * 0.25)


# ── 消息渲染 ─────────────────────────────────────────────────

def render_message(message: Any) -> str:
    """将消息对象渲染为用于 Token 估算的规范文本

    支持 LangChain 消息对象（有 type/content 属性）和普通 dict。
    渲染格式包含 role、tool 名称、tool_call_id 等元信息。

    Args:
        message: 消息对象（LangChain message 或 dict）

    Returns:
        规范化的文本表示
    """
    # 提取基础属性
    if isinstance(message, dict):
        role = message.get("role", "unknown")
        content = message.get("content", "") or ""
        name = message.get("name", "")
        tool_call_id = message.get("tool_call_id", "")
        tool_calls = message.get("tool_calls")
    else:
        role = getattr(message, "type", message.__class__.__name__)
        content = getattr(message, "content", "") or ""
        name = getattr(message, "name", "")
        tool_call_id = getattr(message, "tool_call_id", "")
        tool_calls = getattr(message, "tool_calls", None)

    parts = []

    # Role
    role_label = role.upper() if role != "ai" else "AI"
    parts.append(f"[{role_label}]")

    # Tool name (for ToolMessage)
    if name:
        parts.append(f"[tool:{name}]")

    # Tool call id
    if tool_call_id:
        parts.append(f"[call_id:{tool_call_id}]")

    # Tool calls (for AIMessage with pending calls)
    if tool_calls:
        tc_names = []
        for tc in tool_calls:
            tc_name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
            if tc_name:
                tc_names.append(tc_name)
        if tc_names:
            parts.append(f"[tool_calls:{','.join(tc_names)}]")

    # Content
    if content:
        parts.append(content)

    return " ".join(parts)


# ── 上下文 Token 估算（baseline 感知） ────────────────────────

def estimate_context_tokens(
    messages: list,
    baseline: int | None = None,
    baseline_message_count: int = 0,
) -> int:
    """估算消息列表的 token 总量

    估算策略：
    - 有 usage baseline 且消息数 >= baseline_message_count（无 RemoveMessage）:
      baseline + 新增消息 char/4 估算
    - 无 baseline 或消息数 < baseline_message_count（发生 RemoveMessage）:
      全量 char/4 估算

    Args:
        messages: 当前消息列表
        baseline: LLM 返回的真实 prompt_tokens（可选）
        baseline_message_count: baseline 对应的消息数量

    Returns:
        预估的 token 总量
    """
    current_count = len(messages)

    if baseline is not None and baseline_message_count > 0 and current_count >= baseline_message_count:
        # 增量估算：baseline + 新增消息
        new_messages = messages[baseline_message_count:]
        new_tokens = sum(
            count_tokens(render_message(msg)) for msg in new_messages
        )
        return baseline + new_tokens

    # 全量估算
    return sum(count_tokens(render_message(msg)) for msg in messages)


# ── 上下文超限错误识别 ────────────────────────────────────────

_CONTEXT_LIMIT_MARKERS = [
    "context_length_exceeded",
    "maximum context length",
    "context window",
    "input too long",
    "prompt is too long",
    "token limit",
    "request too large",
]


def is_context_limit_error(error: BaseException) -> bool:
    """判断异常是否由上下文超限导致

    检查异常文本中是否包含已知的上下文超限标记。

    Args:
        error: 异常对象

    Returns:
        是否为上下文超限错误
    """
    text = repr(error).lower()
    return any(marker in text for marker in _CONTEXT_LIMIT_MARKERS)
