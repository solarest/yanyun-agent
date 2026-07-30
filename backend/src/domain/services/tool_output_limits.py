"""Domain service — Tool output truncation limits.

Defines the maximum allowed size for tool outputs in SSE events and
persistent storage, and provides a truncation helper.
"""

MAX_TOOL_OUTPUT_SIZE: int = 51_200  # 50 KB


def truncate_tool_output(output: str | None) -> str:
    """Truncate a tool output string to MAX_TOOL_OUTPUT_SIZE.

    If the output exceeds the limit, it is truncated and a marker
    indicating the original and truncated lengths is appended.

    Args:
        output: The raw tool output string, or None.

    Returns:
        The original string if within limit, or a truncated copy with
        a ``[truncated: …]`` marker appended.
    """
    if output is None:
        return ""
    if len(output) <= MAX_TOOL_OUTPUT_SIZE:
        return output
    return (
        output[:MAX_TOOL_OUTPUT_SIZE]
        + f"\n\n[truncated: {len(output)} chars → {MAX_TOOL_OUTPUT_SIZE} chars]"
    )
