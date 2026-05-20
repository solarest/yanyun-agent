"""领域服务 - Sub-Agent 编排器

负责 sub-agent 的领域逻辑：
- 构建 sub-agent 的 system prompt
- 构建 sub-agent 的初始 AgentState
- 创建过滤后的工具注册表（排除 session_spawn 和 task 系列工具）
"""

from typing import Optional

from src.domain.repositories.tool_registry import IToolRegistry


# Sub-Agent 排除的工具集合
SUB_AGENT_EXCLUDED_TOOLS = frozenset({
    "session_spawn",  # 防止嵌套递归
    "task_create",    # 避免任务管理冲突
    "task_update",    # 避免任务管理冲突
})


class SubAgentOrchestrator:
    """Sub-Agent 领域编排服务

    封装 sub-agent 初始化和工具集过滤的领域逻辑。
    纯领域服务，不依赖基础设施层。
    """

    def build_sub_agent_system_prompt(
        self,
        parent_system_prompt: str,
        description: str,
    ) -> str:
        """组装 sub-agent 的 system prompt

        在主 agent 的 system prompt 基础上添加 sub-agent 任务说明。

        Args:
            parent_system_prompt: 主 agent 的完整 system prompt
            description: sub-agent 的任务描述

        Returns:
            组装后的 sub-agent system prompt
        """
        sub_agent_instruction = (
            "\n\n# Sub-Agent Task Instructions\n\n"
            "You are a sub-agent spawned by the main agent to execute a specific task.\n"
            "Your responsibilities:\n"
            "1. Focus ONLY on the task described below\n"
            "2. Use available tools to complete the task\n"
            "3. Provide a clear, comprehensive result\n\n"
            f"## Your Task\n\n{description}\n\n"
            "Execute this task independently and provide the final result."
        )

        return parent_system_prompt + sub_agent_instruction

    def build_sub_agent_initial_state(
        self,
        *,
        system_prompt: str,
        user_message: str,
        description: str,
        task_id: str,
        workspace: str,
        parent_task_id: str,
        max_turns: int,
        model: str = "gpt-4",
        messages: Optional[list] = None,
    ) -> dict:
        """构建 sub-agent 的初始 AgentState

        Args:
            system_prompt: sub-agent 的 system prompt（已通过 build_sub_agent_system_prompt 组装）
            user_message: 用户原始任务输入
            description: sub-agent 的任务描述
            task_id: sub-agent 的 task ID
            workspace: 工作目录（与主 agent 共享）
            parent_task_id: 父 agent 的 task ID
            max_turns: 最大轮次
            model: LLM 模型名称
            messages: 初始消息列表（可选，默认为空）

        Returns:
            sub-agent 的初始状态字典
        """
        from langchain_core.messages import HumanMessage, SystemMessage

        if messages is None:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_message),
            ]

        return {
            "messages": messages,
            "task_id": task_id,
            "workspace": workspace,
            "user_message": description,
            "task_start_message_count": len(messages),
            "model": model,
            "current_turn": 0,
            "max_turns": max_turns,
            "phase": "idle",
            "should_end": False,
            "is_complete": False,
            "pending_tool_calls": [],
            "tool_results": {},
            "awaiting_user_input": False,
            "last_executed_tool_call_ids": [],
            "loop_detection_count": 0,
            "loop_detected": False,
            "loop_type": None,
            "stuck_detection_count": 0,
            "stuck_detected": False,
            "stuck_type": None,
            "current_llm_text": "",
            "empty_retry_count": 0,
            "planning_retry_count": 0,
            "system_prompt": system_prompt,
            "final_result": None,
            "error": None,
            "observation_summary": None,
            "observation_quality": None,
            "observation_items": [],
            "consecutive_empty_observations": 0,
            "last_error_category": None,
            "compression_strategy": None,
            "is_sub_agent": True,
            "parent_task_id": parent_task_id,
        }

    def create_sub_agent_tool_registry(
        self,
        parent_registry: IToolRegistry,
        allowed_tools: Optional[list[str]] = None,
    ) -> IToolRegistry:
        """创建 sub-agent 的工具注册表

        从父注册表中复制工具，排除指定的工具集合。
        如果提供了 allowed_tools 参数，则只包含列表中的工具。

        Args:
            parent_registry: 父 agent 的工具注册表
            allowed_tools: 允许的工具列表（可选，默认排除 SUB_AGENT_EXCLUDED_TOOLS）

        Returns:
            sub-agent 的工具注册表
        """
        from src.infrastructure.tools.registry import ToolRegistry

        # 复用父注册表的 pipeline
        sub_registry = ToolRegistry()

        for tool in parent_registry.list_tools():
            # 如果指定了 allowed_tools，只包含列表中的工具
            if allowed_tools is not None:
                if tool.name not in allowed_tools:
                    continue
            # 否则排除 SUB_AGENT_EXCLUDED_TOOLS 中的工具
            elif tool.name in SUB_AGENT_EXCLUDED_TOOLS:
                continue

            sub_registry.register(tool)

        return sub_registry
