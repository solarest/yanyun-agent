"""Shim: re-exports from src.infrastructure.tools.register for backward compatibility."""

from src.infrastructure.tools.register.decorator import (  # noqa: F401
    _extract_parameters,
    _parse_docstring_params,
    _python_type_to_schema_type,
    _tool_collector,
    clear_collected_tools,
    get_collected_tools,
    tool,
)
