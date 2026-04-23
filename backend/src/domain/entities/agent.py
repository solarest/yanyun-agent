"""领域层 - Agent 实体"""

import string
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional, Tuple, Union

from src.domain.entities.base import Entity


DEFAULT_SYSTEM_PROMPT_TEMPLATE = (
    "你是 {name}，角色定位：{role}。\n"
    "当前工作目录：{workspace}\n"
    "请根据你的角色定位，认真完成用户交给你的任务。"
)


class SafeFormatter(string.Formatter):
    """安全的字符串格式化器

    遇到缺失的 key 时保留 {key} 原文，而非抛出 KeyError。
    """

    def get_value(self, key: Union[str, int], args: Tuple, kwargs: Dict[str, Any]) -> str:  # type: ignore[override]
        if isinstance(key, str):
            return kwargs.get(key, "{" + key + "}")
        return super().get_value(key, args, kwargs)


_safe_formatter = SafeFormatter()


@dataclass
class Agent(Entity):
    """Agent 实体

    定义一个 AI Agent 的基本属性，包括名称、角色和系统提示词模板。
    通过 render_system_prompt 将模板变量替换为实际值。

    Attributes:
        name: Agent 名称（唯一）
        role: Agent 角色描述
        system_prompt_template: 系统提示词模板，支持 {name}、{role}、{workspace} 等变量
        created_at: 创建时间
        updated_at: 更新时间
    """

    name: str = ""
    role: str = ""
    system_prompt_template: str = DEFAULT_SYSTEM_PROMPT_TEMPLATE
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None

    def render_system_prompt(self, context: Dict[str, str]) -> str:
        """使用上下文变量渲染系统提示词模板

        Args:
            context: 变量字典，如 {"name": "...", "role": "...", "workspace": "..."}

        Returns:
            渲染后的系统提示词字符串。缺失变量保持 {var} 原文。
        """
        return _safe_formatter.format(self.system_prompt_template, **context)
