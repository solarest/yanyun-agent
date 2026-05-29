"""领域层 - PromptTemplate 值对象

表示 Prompt 模板的静态配置，从 Agent 实体提取。
组装逻辑由 PromptAssembleService 负责。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.aggregates.agent.agent import Agent


@dataclass(frozen=True)
class PromptTemplate:
    """Prompt 模板值对象

    定义 Prompt 的静态分层内容，字段直接对应 Agent 的 OpenClaw 7 文件结构。
    工具清单（Layer 5）、技能指令（Layer 8）等动态内容由调用方在组装时提供。
    对话历史由 PromptContextInterface 以消息数组方式管理，不在模板中定义。
    """

    # 基本信息
    id: str
    name: str

    # ==================== 静态前缀层（Layer 1-3）====================
    # 对应 Agent 的 OpenClaw 配置文件，跨请求可缓存

    identity_md: str = ""
    """Layer 1 IDENTITY: 身份定义与系统边界约束（对应 Agent.identity_md）"""

    agents_md: str = ""
    """Layer 2 AGENTS.md: 调度规则与标准作业程序（对应 Agent.agents_md）"""

    bootstrap_md: str = ""
    """Layer 3 BOOTSTRAP.md: 初始化序列与核心系统提示词（对应 Agent.bootstrap_md）"""

    # ==================== 静态后缀层（Layer 10-11）====================
    # 对应 Agent 的 OpenClaw 配置文件，跨请求可缓存

    soul_md: str = ""
    """Layer 10 SOUL.md: 响应语气、行为特征及输出格式（对应 Agent.soul_md）"""

    user_md: str = ""
    """Layer 11 USER.md: 用户画像数据与交互限制（对应 Agent.user_md）"""

    memory_md: str = ""
    """Layer 11 MEMORY.md: 长期记忆与既定规则（对应 Agent.memory_md）
    
    特殊说明：memory_md 的内容同时用于两处：
    - Layer 7 Memory Section: 作为记忆系统读写规则（条件注入，需 memory_enabled）
    - Layer 11 静态后缀: 作为长期记忆上下文
    """

    # ==================== 工具授权声明 ====================

    tools_md: str = ""
    """TOOLS.md: 工具授权注册表及调用参数约束（对应 Agent.tools_md）
    
    特殊处理：
    - tools_md 的约束内容注入到 Layer 4 Universal Behavior 的 tool_usage 准则中
    - Layer 5 Tooling Section 完全由运行时传入的 ToolDef 列表动态生成
    - tools_md 不直接映射到某一层，而是作为工具使用的补充约束
    """

    # ==================== 元数据 ====================

    description: str = ""

    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None

    # ==================== 工厂方法 ====================

    @classmethod
    def from_agent(cls, agent: Agent) -> PromptTemplate:
        """从 Agent 实体提取 7 文件内容构造 PromptTemplate

        这是 Agent 定义域与 Prompt 构建域的唯一桥接点，
        确保两个实体间的映射有明确的入口。

        Args:
            agent: Agent 领域实体（包含 OpenClaw 7 文件内容）

        Returns:
            包含 Agent 静态配置的 PromptTemplate 实例
        """
        return cls(
            id=f"pt-{agent.id}",
            name=agent.name,
            identity_md=agent.identity_md,
            agents_md=agent.agents_md,
            bootstrap_md=agent.bootstrap_md,
            soul_md=agent.soul_md,
            user_md=agent.user_md,
            memory_md=agent.memory_md,
            tools_md=agent.tools_md,
            description=agent.description,
        )
