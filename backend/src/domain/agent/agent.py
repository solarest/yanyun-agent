"""领域层 - Agent 实体（OpenClaw 七文件模式）"""

import json
from dataclasses import dataclass, field
from datetime import datetime

from src.domain.base import Entity

# OpenClaw 配置文件名称常量
CONFIG_FILES = [
    "identity_md",
    "soul_md",
    "agents_md",
    "bootstrap_md",
    "memory_md",
    "tools_md",
    "user_md",
]

MAX_CONFIG_LENGTH = 50000
MAX_VIBES_COUNT = 3


@dataclass
class Agent(Entity):
    """Agent 领域实体（OpenClaw 七文件模式）

    定义一个 AI Agent 的完整配置，包括基本信息、简化表单字段和七个配置文件。
    通过 PromptBuilder 领域服务组装系统提示词。

    Attributes:
        name: Agent 名称（唯一）
        description: Agent 功能描述
        vibes: JSON 数组字符串，存储选中的 vibe 标签
        identity_md ~ user_md: OpenClaw 七个配置文件内容
        config_version: 配置版本号，每次更新配置文件时递增
        created_at: 创建时间
        updated_at: 更新时间
    """

    name: str = ""
    description: str = ""

    # 简化表单字段
    vibes: str = "[]"  # JSON 数组字符串，ORM 直接映射 Text

    # 配置文件内容（OpenClaw 七文件）
    identity_md: str = ""  # IDENTITY.md: 身份定义与系统边界约束
    soul_md: str = ""  # SOUL.md: 响应语气、行为特征及输出格式
    agents_md: str = ""  # AGENTS.md: 调度规则与标准作业程序
    bootstrap_md: str = ""  # BOOTSTRAP.md: 初始化序列与核心系统提示词
    memory_md: str = ""  # MEMORY.md: 长期上下文数据与既定规则（初始为空）
    tools_md: str = ""  # TOOLS.md: 工具授权注册表及调用参数
    user_md: str = ""  # USER.md: 用户画像数据与交互限制

    # 版本管理
    config_version: int = 1

    # 时间戳
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime | None = None

    def set_vibes(self, vibes: list[str]) -> None:
        """设置 vibe 标签（最多 3 个）

        Args:
            vibes: vibe 标签列表

        Raises:
            ValueError: 当 vibes 超过 3 个时
        """
        if len(vibes) > MAX_VIBES_COUNT:
            raise ValueError(f"vibes 最多只能选择 {MAX_VIBES_COUNT} 个")
        self.vibes = json.dumps(vibes, ensure_ascii=False)

    def get_vibes(self) -> list[str]:
        """获取 vibe 标签列表

        Returns:
            vibe 标签字符串列表
        """
        if isinstance(self.vibes, list):
            return self.vibes
        return json.loads(self.vibes)

    def update_config(self, **config_fields: str) -> None:
        """更新配置文件，自动递增版本号

        Args:
            **config_fields: 配置文件字段，键名为 identity_md/soul_md/agents_md/
                             bootstrap_md/memory_md/tools_md/user_md

        Raises:
            ValueError: 当单个配置文件内容超过 50000 字符时
        """
        for field_name, value in config_fields.items():
            if field_name not in CONFIG_FILES or value is None:
                continue
            if len(value) > MAX_CONFIG_LENGTH:
                raise ValueError(f"{field_name} 内容超过 {MAX_CONFIG_LENGTH} 字符限制")
            setattr(self, field_name, value)
        self.config_version += 1
        self.updated_at = datetime.now()
