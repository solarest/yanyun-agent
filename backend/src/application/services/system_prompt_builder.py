"""应用层 - System Prompt 构建器

封装 PromptAssembleService 调用 + sub-agent/team mode 分支。
原作 AgentLoopRunner._build_system_prompt()。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from src.domain.services.prompt_assemble_service import PromptAssembleService
from src.domain.value_objects.prompt_template import PromptTemplate

if TYPE_CHECKING:
    from src.domain.repositories.tool_registry import IToolRegistry
    from src.domain.skills import ISkillRepository
    from src.domain.repositories.agent_repository import IAgentRepository

logger = logging.getLogger(__name__)


class SystemPromptBuilder:
    """构建 Agent 的 system prompt（11 层架构 + 模式分支）"""

    def __init__(
        self,
        agent_repo: IAgentRepository,
        tool_registry: Optional[IToolRegistry] = None,
        skill_repo: Optional[ISkillRepository] = None,
        assemble_service: Optional[PromptAssembleService] = None,
    ):
        self._agent_repo = agent_repo
        self._tool_registry = tool_registry
        self._skill_repo = skill_repo
        self._assemble_service = assemble_service or PromptAssembleService()

    async def build(
        self,
        agent_id: str,
        workspace: str,
        skill_ids: Optional[list[str]] = None,
        team_context: Optional[str] = None,
        is_sub_agent: bool = False,
        parent_system_prompt: Optional[str] = None,
        sub_agent_description: Optional[str] = None,
        team_mode: bool = False,
    ) -> str:
        """构建 system prompt

        Args:
            agent_id: Agent ID
            workspace: 工作目录
            skill_ids: 选中的 Skill ID 列表
            team_context: team mode 的 prompt 注入内容
            is_sub_agent: 是否为 sub-agent 模式
            parent_system_prompt: 父 agent 的 system prompt
            sub_agent_description: sub-agent 任务描述
            team_mode: 是否为 team mode

        Returns:
            完整的 system prompt 字符串
        """
        agent = await self._agent_repo.get_by_id(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        template = PromptTemplate.from_agent(agent)

        # 从 ToolRegistry 获取 ToolDef 列表（用于 Layer 5 工具描述）
        tool_defs = []
        if self._tool_registry:
            tool_defs = self._tool_registry.get_tool_defs()

        # 从 SkillRepository 获取选中的 SkillDef 列表（用于 Layer 8 注入）
        skill_defs = []
        if self._skill_repo and skill_ids:
            skill_defs = await self._skill_repo.get_by_ids(skill_ids)

        assembly_result = self._assemble_service.assemble(
            template=template,
            tools=tool_defs,
            skills=skill_defs,
            workspace=workspace,
            environment={
                "platform": "darwin",
                "date": datetime.now().strftime("%Y-%m-%d"),
                "timezone": "Asia/Shanghai",
            },
            memory_enabled=bool(template.memory_md),
            team_context=team_context,
        )
        agent_system_prompt = assembly_result.system_message

        logger.info(
            "[Prompt Assembly] agent=%s | layers=%s | total_tokens=%d | static_prefix_tokens=%d",
            agent_id,
            assembly_result.layers,
            assembly_result.total_token_estimate,
            assembly_result.static_prefix_tokens,
        )

        return self._apply_mode(
            agent_system_prompt,
            is_sub_agent=is_sub_agent,
            parent_system_prompt=parent_system_prompt,
            sub_agent_description=sub_agent_description,
            team_mode=team_mode,
        )

    def _apply_mode(
        self,
        agent_system_prompt: str,
        is_sub_agent: bool,
        parent_system_prompt: Optional[str],
        sub_agent_description: Optional[str],
        team_mode: bool,
    ) -> str:
        """根据模式调整 system prompt"""
        if team_mode:
            return agent_system_prompt

        if not is_sub_agent:
            return agent_system_prompt

        from src.domain.services.sub_agent_orchestrator import SubAgentOrchestrator
        orchestrator = SubAgentOrchestrator()
        return orchestrator.build_sub_agent_system_prompt(
            parent_system_prompt=parent_system_prompt or "",
            description=sub_agent_description or "",
        )
