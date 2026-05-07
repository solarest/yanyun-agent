"""领域层 - Prompt 组装服务"""

from typing import Optional
from src.domain.entities.prompt_template import PromptTemplate
from src.domain.entities.prompt_assembly_result import PromptAssemblyResult
from src.domain.entities.tool import ToolDef
from src.domain.entities.skill_def import SkillDef
from src.domain.entities.output_schema import OutputSchema
from src.domain.services.token_utils import count_tokens


class PromptAssembleService:
    """Prompt 组装领域服务

    负责将 11 层 Prompt 组件组装为 system_message 字符串。
    纯领域逻辑，不涉及存储或外部依赖。

    职责边界：
    - 负责：构建 system_message（11 层拼接）
    - 不负责：对话历史管理（由 PromptContextInterface 处理）
    - 不负责：最终 messages 数组构建（由 agent-loop 通过 PromptContextInterface 完成）
    """

    def assemble(
        self,
        template: PromptTemplate,
        tools: Optional[list[ToolDef]] = None,
        skills: Optional[list[SkillDef]] = None,
        output_schema: Optional[OutputSchema] = None,
        task: Optional[str] = None,
        memory_enabled: bool = False,
        workspace: str = "",
        environment: Optional[dict] = None,
    ) -> PromptAssemblyResult:
        """组装 system_message（11 层结构）

        按 Agent 7 文件定义的层级顺序组装，输出作为 LLM API 中
        {"role": "system", "content": system_message} 的内容。

        Args:
            template: Prompt 模板（从 Agent 7 文件构造）
            tools: 工具定义列表（由 Tools Hub 提供，用于 Layer 5）
            skills: 技能定义列表（由 Skills 模块提供，用于 Layer 8）
            output_schema: 输出 Schema（可选）
            task: 当前任务描述（可选）
            memory_enabled: 是否启用记忆系统（控制 Layer 7 注入）
            workspace: 工作目录路径（Layer 6）
            environment: 环境上下文，如 {"platform": "...", "date": "...", "timezone": "..."}（Layer 9）

        Returns:
            PromptAssemblyResult，包含 system_message 和元信息
        """
        parts = []
        layer_info = {}
        tools = tools or []
        skills = skills or []

        # ==================== 静态前缀（Layer 1-3）====================
        # 顺序：BOOTSTRAP → IDENTITY → AGENTS

        static_prefix = self._build_static_prefix(template)
        if static_prefix:
            parts.append(static_prefix)
            layer_info["static_prefix"] = True

        static_prefix_tokens = count_tokens(static_prefix)

        # ==================== CACHE BOUNDARY ====================
        parts.append("── CACHE BOUNDARY ─────────────────────────────────────")

        # ==================== 动态中间层（Layer 4-9）====================

        # Layer 4: Universal Behavior（8 大行为准则，条件注入）
        universal_behavior = self._build_universal_behavior(
            tools=tools,
            skills=skills,
            memory_enabled=memory_enabled,
            tools_md=template.tools_md,
        )
        if universal_behavior:
            parts.append("# Universal Behavior\n\n" + universal_behavior)
            layer_info["universal_behavior"] = True

        # Layer 5: 工具名称列表（详细信息通过 bind_tools() 传递）
        if tools:
            tools_section = "# Available Tools\n\n" + "\n".join(
                t.to_prompt_section() for t in tools
            )
            parts.append(tools_section)
            layer_info["tools_count"] = len(tools)

        # Layer 6: 工作目录
        if workspace:
            parts.append(
                f"# Workspace\n\nCurrent working directory: {workspace}")
            layer_info["workspace"] = workspace

        # Layer 7: 记忆系统（条件注入：memory_enabled 为 True 时）
        if memory_enabled and template.memory_md:
            parts.append("# Memory System\n\n" + template.memory_md)
            layer_info["memory_enabled"] = True

        # Layer 8: Skill Instructions
        if skills:
            skills_section = self._build_skill_instructions(skills)
            parts.append(skills_section)
            layer_info["skills_count"] = len(skills)

        # Layer 9: 环境上下文
        if environment:
            env_parts = []
            if "platform" in environment:
                env_parts.append(f"Platform: {environment['platform']}")
            if "date" in environment:
                env_parts.append(f"Date: {environment['date']}")
            if "timezone" in environment:
                env_parts.append(f"Timezone: {environment['timezone']}")
            if env_parts:
                parts.append("# Environment\n\n" + "\n".join(env_parts))
                layer_info["environment"] = True

        # ==================== STATIC SUFFIX ====================
        parts.append("── STATIC SUFFIX ──────────────────────────────────────")

        # ==================== 静态后缀（Layer 10-11）====================
        # 顺序：SOUL → USER → MEMORY

        static_suffix = self._build_static_suffix(template)
        if static_suffix:
            parts.append(static_suffix)
            layer_info["static_suffix"] = True

        # ==================== 可选附加层 ====================

        # 输出格式层
        if output_schema:
            schema_section = (
                "# Output Format\n\n"
                "Respond with a valid JSON object matching this schema:\n\n"
                + output_schema.to_json_string()
            )
            parts.append(schema_section)
            layer_info["has_schema"] = True

        # 任务说明层
        if task:
            parts.append("# Current Task\n" + task)
            layer_info["task"] = True

        # ==================== 组装结果 ====================

        system_message = "\n\n".join(parts)
        total_tokens = count_tokens(system_message)

        return PromptAssemblyResult(
            system_message=system_message,
            static_prefix_tokens=static_prefix_tokens,
            total_token_estimate=total_tokens,
            layers=layer_info,
        )

    def _build_universal_behavior(
        self,
        tools: list[ToolDef],
        skills: list[SkillDef],
        memory_enabled: bool,
        tools_md: str = "",
    ) -> str:
        """构建 Universal Behavior 层（8 大行为准则，条件注入）

        Args:
            tools: 可用工具列表
            skills: 已加载 Skill 列表
            memory_enabled: 是否启用记忆系统
            tools_md: Agent TOOLS.md 中的工具授权约束
                （补充到 tool_usage 准则末尾，见 tools_md 特殊处理说明）

        Returns:
            条件注入后的行为准则文本
        """
        parts = []

        # 总是注入的准则（Always-On Rules）
        parts.append(self._TONE_AND_STYLE)
        parts.append(self._PROFESSIONAL_OBJECTIVITY)
        parts.append(self._PROACTIVENESS)

        # 条件注入：任务管理（有 task_* 工具时）
        if any(t.name.startswith("task_") for t in tools):
            parts.append(self._TASK_MANAGEMENT)

        # 条件注入：委派策略（有 sessions_* 工具时）
        if any(t.name.startswith("sessions_") for t in tools):
            parts.append(self._DELEGATION_STRATEGY)

        # 条件注入：工具使用规范（有可用工具时）
        # 若 tools_md 非空，将 TOOLS.md 中的静态授权约束附加到 tool_usage 末尾
        if tools:
            tool_usage = self._TOOL_USAGE
            if tools_md:
                tool_usage += "\n\n### Tool Authorization Constraints\n\n" + tools_md
            parts.append(tool_usage)

        # 条件注入：记忆使用规范（启用 Memory 时）
        if memory_enabled:
            parts.append(self._MEMORY_USAGE)

        # 条件注入：Skill 使用规范（有已加载 Skill 时）
        if skills:
            parts.append(self._SKILL_USAGE)

        return "\n\n".join(parts)

    def _build_static_prefix(self, template: PromptTemplate) -> str:
        """组装静态前缀层内容（Layer 1-3）

        组装顺序：BOOTSTRAP → IDENTITY → AGENTS

        Args:
            template: Prompt 模板

        Returns:
            拼接后的静态前缀字符串
        """
        sections = [
            ("Bootstrap", template.bootstrap_md),
            ("Identity", template.identity_md),
            ("Agents", template.agents_md),
        ]

        parts = []
        for title, content in sections:
            if content:
                parts.append(f"# {title}\n{content}")

        return "\n\n".join(parts)

    def _build_static_suffix(self, template: PromptTemplate) -> str:
        """组装静态后缀层内容（Layer 10-11）

        组装顺序：SOUL → USER → MEMORY

        Args:
            template: Prompt 模板

        Returns:
            拼接后的静态后缀字符串
        """
        sections = [
            ("Soul", template.soul_md),
            ("User", template.user_md),
            ("Memory", template.memory_md),
        ]

        parts = []
        for title, content in sections:
            if content:
                parts.append(f"# {title}\n{content}")

        return "\n\n".join(parts)

    def _build_skill_instructions(self, skills: list[SkillDef]) -> str:
        """构建 Layer 8 Skill Instructions

        Args:
            skills: 已加载的 Skill 列表

        Returns:
            `<active_skills>` 标签包裹的 Skill 指令文本
        """
        parts = ["<active_skills>"]
        for skill in skills:
            parts.append(f"## {skill.name}")
            parts.append(skill.to_prompt_section())
        parts.append("</active_skills>")

        return "\n\n".join(parts)

    # ==================== 8 大行为准则模板 ====================

    _TONE_AND_STYLE = """## Communication Style

- Respond in the same language as the user's input
- Maintain a professional, concise, and friendly tone
- Lead with conclusions, then provide detailed explanations
- Avoid overly technical jargon unless the user demonstrates expertise
- Use structured formatting (lists, tables, code blocks) for readability"""

    _PROFESSIONAL_OBJECTIVITY = """## Professional Objectivity

- Present balanced views with pros and cons of approaches
- Explicitly acknowledge uncertainty rather than guessing
- Distinguish between factual statements and recommendations
- Present multiple mainstream perspectives on contentious topics
- Avoid absolutist language ("must", "always"); use "recommend", "typically\""""

    _PROACTIVENESS = """## Proactiveness

- Identify implicit but relevant needs and offer suggestions
- Proactively warn about potential issues (security risks, performance concerns)
- Suggest next steps without imposing them
- After task completion, ask if further assistance is needed
- Boundary: Don't over-speculate; confirm before major decisions"""

    _TASK_MANAGEMENT = """## Task Management

You have access to task management tools. Follow these rules:

- Create tasks before executing multi-step workflows
- Create separate task records for each independent subtask
- Update task status promptly upon completion
- Establish correct dependencies between related tasks
- When users request progress updates, use task list tools to provide status reports"""

    _DELEGATION_STRATEGY = """## Delegation Strategy

You have access to session delegation tools. Follow these rules:

- Delegate independent, parallelizable subtasks to sub-sessions
- Provide clear task descriptions and expected outputs when delegating
- Monitor delegated task progress and intervene when necessary
- Never delegate within sub-sessions (avoid infinite recursion)
- Don't delegate simple tasks (single-step, no dependencies); execute directly"""

    _TOOL_USAGE = """## Tool Usage Guidelines

You have access to external tools. Follow these rules:

- Verify parameters are correct and complete before calling tools
- When tool calls fail, analyze errors and attempt fixes or retries
- Don't call the same tool more than 3 times consecutively without changing parameters
- Confirm with users before dangerous operations (delete, overwrite, send)
- Prefer specialized tools over generic ones (e.g., `read_file` over `execute_command`)"""

    _MEMORY_USAGE = """## Memory System Usage

You have access to a memory system. Follow these rules:

- Read relevant memories at conversation start to understand user preferences and context
- Write important information (preferences, key decisions, action items) to memory promptly
- Don't store temporary or one-time information
- When memory conflicts with current context, prioritize current information and update memory
- Respect user privacy; never record sensitive information (passwords, keys, personal data)"""

    _SKILL_USAGE = """## Skill Usage Guidelines

You have access to specialized skills. Follow these rules:

- When user requests match skill triggers, use the corresponding skill instead of handling manually
- Follow skill-defined steps strictly; don't skip critical steps
- Handle errors during skill execution according to the skill's error handling flow
- If multiple skills match, choose the most specific one
- Don't modify skill-defined steps or parameters on your own"""
