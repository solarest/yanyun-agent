"""基础设施层 - @tool 装饰器

通过装饰器声明式定义工具，自动从函数签名提取参数 Schema，
自动注册到全局收集器，后由 ToolRegistry 统一注册。
"""

import asyncio
import functools
import inspect
import json
import logging
import time
from typing import Any, Callable, Optional, get_type_hints

from src.domain.tool import (
    RegisteredTool,
    ToolContext,
    ToolParameter,
    ToolPolicy,
    ToolResult,
)

# 独立的工具调用日志记录器（每个工具在其具体实现点自动产出日志）
tool_logger = logging.getLogger("tool.call")


# 全局工具收集器（模块加载时收集，后由 Registry 统一注册）
_tool_collector: list[RegisteredTool] = []


def get_collected_tools() -> list[RegisteredTool]:
    """获取所有通过 @tool 装饰器收集的工具"""
    return list(_tool_collector)


def clear_collected_tools() -> None:
    """清空收集器（用于测试隔离）"""
    _tool_collector.clear()


def tool(
    name: Optional[str] = None,
    description: str = "",
    category: str = "general",
    returns: str = "",
    timeout_ms: int = 30000,
    max_calls_per_minute: int = 60,
    sandboxed: bool = False,
) -> Callable:
    """工具定义装饰器

    使用方式::

        @tool(
            name="web_search",
            description="搜索网络获取实时信息",
            category="web_search",
        )
        async def web_search(query: str, max_results: int = 5) -> ToolResult:
            '''
            Args:
                query: 搜索关键词
                max_results: 最大返回结果数
            '''
            ...

    装饰器自动完成：
    1. 从函数签名提取参数类型和默认值
    2. 从 docstring 提取参数描述
    3. 构建 ToolParameter 列表
    4. 创建 RegisteredTool 并加入收集器
    """

    def decorator(func: Callable) -> Callable:
        tool_name = name or func.__name__
        tool_desc = description or (func.__doc__ or "").split("\n")[0].strip()

        parameters = _extract_parameters(func)

        policy = ToolPolicy(
            timeout_ms=timeout_ms,
            max_calls_per_minute=max_calls_per_minute,
            sandboxed=sandboxed,
        )

        wrapped = _wrap_tool_function(func)

        registered = RegisteredTool(
            name=tool_name,
            description=tool_desc,
            func=wrapped,
            parameters=parameters,
            returns=returns,
            category=category,
            policy=policy,
        )

        _tool_collector.append(registered)

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await wrapped(*args, **kwargs)

        # 在 wrapper 上附加元数据，便于测试和内省
        wrapper._registered_tool = registered  # type: ignore[attr-defined]

        return wrapper

    return decorator


def _extract_parameters(func: Callable) -> list[ToolParameter]:
    """从函数签名和 docstring 提取参数定义

    支持的类型映射：
    - str -> "string"
    - int -> "integer"
    - float -> "number"
    - bool -> "boolean"
    - list -> "array"
    - dict -> "object"
    """
    sig = inspect.signature(func)
    try:
        type_hints = get_type_hints(func)
    except Exception:
        type_hints = {}
    doc_params = _parse_docstring_params(func.__doc__ or "")

    parameters: list[ToolParameter] = []
    for param_name, param in sig.parameters.items():
        # 跳过 self、context 参数
        if param_name in ("self", "context", "ctx"):
            continue

        param_type = type_hints.get(param_name, str)
        type_str = _python_type_to_schema_type(param_type)

        required = param.default is inspect.Parameter.empty

        desc = doc_params.get(param_name, "")

        parameters.append(
            ToolParameter(
                name=param_name,
                type=type_str,
                description=desc,
                required=required,
            )
        )

    return parameters


def _python_type_to_schema_type(py_type: Any) -> str:
    """Python 类型到 JSON Schema 类型的映射"""
    type_map: dict[type, str] = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
    }
    # 处理 Optional / Union 等泛型
    origin = getattr(py_type, "__origin__", None)
    if origin is list:
        return "array"
    if origin is dict:
        return "object"
    # 处理 Optional[T] 或 Union[T, None] - 提取实际类型
    if origin is not None:
        # Optional[X] 实际上是 Union[X, None]
        # 获取第一个非 None 的类型参数
        args = getattr(py_type, "__args__", None)
        if args:
            # 找到第一个不是 NoneType 的参数
            for arg in args:
                if arg is type(None):
                    continue
                # 递归处理实际类型
                return _python_type_to_schema_type(arg)
    return type_map.get(py_type, "string")


def _parse_docstring_params(docstring: str) -> dict[str, str]:
    """从 Google-style docstring 解析 Args 段落"""
    params: dict[str, str] = {}
    in_args = False
    current_param: Optional[str] = None

    for line in docstring.split("\n"):
        stripped = line.strip()
        if stripped.lower().startswith("args:"):
            in_args = True
            continue
        if in_args:
            if stripped.lower().startswith(("returns:", "raises:", "note:")):
                break
            if stripped and not stripped.startswith("-") and ":" in stripped:
                parts = stripped.split(":", 1)
                current_param = parts[0].strip()
                params[current_param] = parts[1].strip()
            elif current_param and stripped:
                params[current_param] += " " + stripped

    return params


def _wrap_tool_function(func: Callable) -> Callable:
    """包装工具函数为统一的异步调用接口

    统一签名：async def(input: dict, context: ToolContext | None) -> ToolResult

    同时在此处产出独立的工具调用日志（tool.call），记录：
    - 工具名、task_id、完整输入
    - 执行过程（start / end / exception）与耗时
    - 完整输出（含 success / error / metadata）
    """
    sig = inspect.signature(func)
    is_async = inspect.iscoroutinefunction(func)
    tool_name = getattr(func, "__name__", "<anonymous>")

    accepts_context = "context" in sig.parameters or "ctx" in sig.parameters

    async def wrapped(input: dict[str, Any], context: Optional[ToolContext] = None) -> ToolResult:
        task_id = getattr(context, "task_id", None) if context else None

        # === 工具日志：开始 ===
        tool_logger.info(
            "[TOOL-CALL] task_id=%s tool=%s phase=start input=%s",
            task_id,
            tool_name,
            json.dumps(input, ensure_ascii=False, default=str),
        )

        kwargs = dict(input)
        if accepts_context and context:
            ctx_name = "context" if "context" in sig.parameters else "ctx"
            kwargs[ctx_name] = context

        start_time = time.time()
        try:
            if is_async:
                result = await func(**kwargs)
            else:
                result = await asyncio.to_thread(func, **kwargs)
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            # === 工具日志：异常 ===
            tool_logger.exception(
                "[TOOL-CALL] task_id=%s tool=%s phase=exception duration_ms=%s error=%s",
                task_id,
                tool_name,
                duration_ms,
                str(e),
            )
            raise

        duration_ms = int((time.time() - start_time) * 1000)

        # 规范化返回值
        if isinstance(result, ToolResult):
            normalized = result
        elif isinstance(result, str):
            normalized = ToolResult(output=result)
        elif isinstance(result, dict):
            normalized = ToolResult(
                output=result.get("output", str(result)),
                success=result.get("success", True),
                metadata=result.get("metadata", {}),
            )
        else:
            normalized = ToolResult(output=str(result))

        # === 工具日志：完成 ===
        tool_logger.info(
            "[TOOL-CALL] task_id=%s tool=%s phase=end status=%s duration_ms=%s output=%s",
            task_id,
            tool_name,
            "success" if normalized.success else "error",
            duration_ms,
            json.dumps(
                {
                    "output": normalized.output,
                    "success": normalized.success,
                    "error": normalized.error,
                    "metadata": normalized.metadata,
                },
                ensure_ascii=False,
                default=str,
            ),
        )

        return normalized

    return wrapped
