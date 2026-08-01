"""Domain service — Tool output truncation limits.

Defines the maximum allowed size for tool outputs in SSE events and
persistent storage, and provides truncation helpers for each path.
"""

MAX_TOOL_OUTPUT_SIZE: int = 51_200  # 50 KB


def truncate_tool_output(output: str | None) -> str:
    """Truncate a tool output string to MAX_TOOL_OUTPUT_SIZE.

    Used for SSE live push to clients. If the output exceeds the limit,
    it is truncated and a marker indicating the original and truncated
    lengths is appended.

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


def truncate_tool_output_for_db(
    output: str | None, *, ref: str | None = None
) -> dict:
    """Truncate tool output for DB storage, with optional file reference.

    Returns a dict with ``result`` (truncated or full) and optionally
    ``full_result_ref`` pointing to the complete output file.

    Args:
        output: The raw tool output string, or None.
        ref: Relative path to the complete output file (e.g.
             ``tool_results/call_abc.txt``). Only included when output
             was actually truncated.

    Returns:
        A dict with ``result`` (str) and optionally ``full_result_ref`` (str).
    """
    if not output:
        return {"result": ""}
    if len(output) <= MAX_TOOL_OUTPUT_SIZE:
        return {"result": output}
    truncated = (
        output[:MAX_TOOL_OUTPUT_SIZE]
        + f"\n\n[truncated: {len(output)} chars → {MAX_TOOL_OUTPUT_SIZE} chars]"
    )
    result: dict = {"result": truncated}
    if ref:
        result["full_result_ref"] = ref
    return result
