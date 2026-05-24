"""应用层 - SendMessage 用例

核心编排用例：用户发送消息 → 创建 Task → 异步启动 Agent Loop。
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from langchain_core.messages import AIMessage, HumanMessage

from src.application.use_cases.agent_workflow import AgentWorkflowBuilder
from src.domain.conversation.session_message import (
    MessageStatus,
    SessionMessage,
    SessionMessageRole,
)
from src.domain.task.task import Task, TaskConfig, TaskStatus
from src.domain.llm.interfaces.llm_provider import ILLMProvider
from src.domain.repositories.agent_repository import IAgentRepository
from src.domain.repositories.session_message_repository import (
    ISessionMessageRepository,
)
from src.domain.repositories.session_repository import ISessionRepository
from src.domain.repositories.skill_repository import ISkillRepository
from src.domain.repositories.task_repository import ITaskRepository
from src.domain.repositories.tool_registry import IToolRegistry
from src.domain.services import IEventEmitter, ProxyEventEmitter
from src.domain.prompt.prompt_template import PromptTemplate
from src.domain.services.prompt_assemble_service import PromptAssembleService

logger = logging.getLogger(__name__)


def _tool_defs_to_openai_functions(tool_registry: IToolRegistry) -> list:
    """将工具转换为 OpenAI function schema 格式（供 bind_tools 使用）"""
    return [tool.to_tool_def().to_llm_schema() for tool in tool_registry.list_tools()]


def _build_message_event_payload(message: SessionMessage) -> Dict[str, Any]:
    """构建 session:message:saved 事件载荷。"""
    return {
        "message": {
            "id": message.id,
            "session_id": message.session_id,
            "task_id": message.task_id,
            "role": message.role.value,
            "content": message.content,
            "tool_calls": message.tool_calls,
            "tool_results": message.tool_results,
            "status": message.status.value,
            "error": message.error,
            "cost": message.cost,
            "created_at": message.created_at.isoformat(),
        }
    }


def _tool_output_text(tool_result: Dict[str, Any]) -> str:
    """统一提取工具结果的文本：优先 output，其次 error，都没有返回空串。"""
    return tool_result.get("output") or tool_result.get("error") or ""


def _extract_last_message_content(messages: list) -> str:
    """从消息列表倒序查找第一条非空 content，找不到返回空串。

    兼容 dict 和 LangChain Message 对象两种形式。
    """
    for msg in reversed(messages):
        if isinstance(msg, dict):
            content = msg.get("content", "")
        else:
            content = getattr(msg, "content", "") or ""
        if content:
            return content
    return ""


class SendMessageUseCase:
    """发送消息用例 — 编排 Session 操作 + Agent Loop 启动"""

    def __init__(
        self,
        agent_repo: IAgentRepository,
        session_repo: ISessionRepository,
        message_repo: ISessionMessageRepository,
        task_repo: Optional[ITaskRepository] = None,
        event_emitter: Optional[IEventEmitter] = None,
        tool_registry: Optional[IToolRegistry] = None,
        skill_repo: Optional[ISkillRepository] = None,
        llm_provider: Optional[ILLMProvider] = None,
        running_tasks: Optional[dict[str, asyncio.Task]] = None,
        sub_agent_launcher: Optional[Any] = None,
    ):
        self.agent_repo = agent_repo
        self.session_repo = session_repo
        self.message_repo = message_repo
        self.task_repo = task_repo
        self.event_emitter = event_emitter
        self.tool_registry = tool_registry
        self.skill_repo = skill_repo
        self.llm_provider = llm_provider
        self.running_tasks = running_tasks if running_tasks is not None else {}
        self.sub_agent_launcher = sub_agent_launcher

    async def execute(
        self,
        agent_id: str,
        session_id: str,
        content: str,
        model: Optional[str] = None,
        max_turns: int = 100,
        workspace: str = "/tmp/agent-workspace",
        skill_ids: Optional[list[str]] = None,
        # Sub-agent 模式参数
        is_sub_agent: bool = False,
        parent_task_id: Optional[str] = None,
        sub_agent_description: Optional[str] = None,
        parent_system_prompt: Optional[str] = None,
        sub_task: Optional[Task] = None,
        allowed_tools: Optional[list[str]] = None,
    ) -> Dict[str, Any]:
        """执行发送消息流程

        同步部分（HTTP 请求内完成，返回 202）:
        1. 保存 user SessionMessage
        2. 更新 Session 元数据
        3. 创建 Task
        4. asyncio.create_task 启动后台 runner
        5. 返回 taskId + userMessage

        Args:
            agent_id: Agent ID
            session_id: Session ID
            content: 消息内容
            model: LLM 模型名称
            max_turns: 最大轮次
            workspace: 工作目录
            skill_ids: 选中的 Skill ID 列表
            is_sub_agent: 是否为 sub-agent 模式
            parent_task_id: 父 task ID（sub-agent 模式）
            sub_agent_description: sub-agent 任务描述（sub-agent 模式）
            parent_system_prompt: 父 agent 的 system prompt（sub-agent 模式）
            sub_task: sub-task 实体（sub-agent 模式）
            allowed_tools: 允许的工具列表（sub-agent 模式）

        Returns:
            {"user_message": SessionMessage, "task_id": str}
        """
        persist_session_messages = not is_sub_agent

        # 1. 保存用户消息。sub-agent 的中间对话不写入父 session，最终结果通过
        #    Task.result 和 session_spawn 的 ToolMessage 回到主 agent。
        user_msg: Optional[SessionMessage] = None
        if persist_session_messages:
            user_msg = SessionMessage(
                session_id=session_id,
                role=SessionMessageRole.USER,
                content=content,
                status=MessageStatus.COMPLETED,
            )
            user_msg = await self.message_repo.add(user_msg)

            # 2. 更新 Session 元数据
            session = await self.session_repo.get_by_id(session_id)
            if session:
                session.update_metadata(content)
                # 首条消息自动生成标题 - 使用 LLM 提炼
                if session.message_count == 1:
                    # 异步生成标题，不阻塞主流程
                    asyncio.create_task(
                        self._generate_session_title(session_id, content)
                    )
                await self.session_repo.update(session)

        # 3. 创建 Task
        from src.infrastructure.llm.config import LLMSettings

        effective_model = model or LLMSettings().default_model
        if sub_task is not None:
            task = sub_task
            task.status = TaskStatus.RUNNING
            task.started_at = task.started_at or datetime.now()
        else:
            task = Task(
                message=content,
                workspace=workspace,
                status=TaskStatus.RUNNING,
                model=effective_model,
                config=TaskConfig(max_turns=max_turns),
                max_turns=max_turns,
                agent_id=agent_id,
                session_id=session_id,
                started_at=datetime.now(),
            )
        if self.task_repo and sub_task is None:
            task = await self.task_repo.add(task)

        # 4. 启动后台 runner
        asyncio_task: asyncio.Task | None = None
        if self.event_emitter and self.tool_registry:
            asyncio_task = asyncio.create_task(
                self._run_agent_loop(
                    agent_id=agent_id,
                    session_id=session_id,
                    task=task,
                    content=content,
                    model=effective_model,
                    max_turns=max_turns,
                    workspace=workspace,
                    skill_ids=skill_ids or [],
                    is_sub_agent=is_sub_agent,
                    parent_task_id=parent_task_id,
                    sub_agent_description=sub_agent_description,
                    parent_system_prompt=parent_system_prompt,
                    allowed_tools=allowed_tools,
                    persist_session_messages=persist_session_messages,
                )
            )
            self.running_tasks[task.id] = asyncio_task
            asyncio_task.add_done_callback(
                lambda t: logger.info("Agent loop task %s finished", task.id)
            )
            asyncio_task.add_done_callback(
                lambda _t: self.running_tasks.pop(task.id, None)
            )

        return {
            "user_message": user_msg,
            "task_id": task.id,
            "asyncio_task": asyncio_task if (self.event_emitter and self.tool_registry) else None,
        }

    def _build_llm(self, model: Optional[str], tool_registry: Optional[IToolRegistry], agent_id: str):
        # 使用注入的 LLM Provider
        llm = self.llm_provider.create_chat_model(
            model=model or None) if self.llm_provider else None
        if llm is None:
            raise RuntimeError("LLM Provider is not configured")

        if tool_registry and tool_registry.tool_count > 0:
            tool_schemas = _tool_defs_to_openai_functions(tool_registry)
            llm = llm.bind_tools(tool_schemas)
            logger.info("binding-tools agent %s Tool schemas: %s",
                        agent_id, tool_schemas)
        return llm

    def _build_graph_config(
        self,
        llm,
        tool_registry: Optional[IToolRegistry],
        agent_id: str,
        model: Optional[str],
        sub_agent_launcher: Optional[Any] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "configurable": {
                "llm": llm,
                "event_emitter": self.event_emitter,
                "event_service": self.event_emitter,
                "tool_registry": tool_registry,
                "agent_id": agent_id,
                "llm_model": model,
                "sub_agent_launcher": sub_agent_launcher,
                "session_id": session_id,
            }
        }

    def _build_system_prompt(
        self,
        is_sub_agent: bool,
        parent_system_prompt: Optional[str],
        sub_agent_description: Optional[str],
        agent_system_prompt: str,
    ) -> str:
        """根据模式构建 system prompt

        Args:
            is_sub_agent: 是否为 sub-agent 模式
            parent_system_prompt: 父 agent 的 system prompt
            sub_agent_description: sub-agent 任务描述
            agent_system_prompt: 当前 agent 的 system prompt（通过 PromptAssembleService 生成）

        Returns:
            构建后的 system prompt
        """
        if not is_sub_agent:
            return agent_system_prompt

        # Sub-agent 模式：复用父 prompt + 添加任务说明
        from src.domain.services.sub_agent_orchestrator import SubAgentOrchestrator
        orchestrator = SubAgentOrchestrator()
        return orchestrator.build_sub_agent_system_prompt(
            parent_system_prompt=parent_system_prompt or "",
            description=sub_agent_description or "",
        )

    def _build_tool_registry(
        self,
        is_sub_agent: bool,
        allowed_tools: Optional[list[str]] = None,
    ) -> Optional[IToolRegistry]:
        """根据模式构建工具注册表

        Args:
            is_sub_agent: 是否为 sub-agent 模式
            allowed_tools: 允许的工具列表

        Returns:
            工具注册表
        """
        if not is_sub_agent:
            return self.tool_registry

        # Sub-agent 模式：排除特定工具
        from src.domain.services.sub_agent_orchestrator import SubAgentOrchestrator
        orchestrator = SubAgentOrchestrator()
        return orchestrator.create_sub_agent_tool_registry(
            self.tool_registry,
            allowed_tools=allowed_tools,
        )

    def _build_event_emitter(
        self,
        is_sub_agent: bool,
        parent_task_id: Optional[str],
        sub_task_id: Optional[str],
    ) -> Optional[IEventEmitter]:
        """根据模式构建事件发射器

        Args:
            is_sub_agent: 是否为 sub-agent 模式
            parent_task_id: 父 task ID
            sub_task_id: 子 task ID

        Returns:
            事件发射器
        """
        if not is_sub_agent:
            return self.event_emitter

        # Sub-agent 模式：使用代理转发器
        return ProxyEventEmitter(
            self.event_emitter,
            parent_task_id=parent_task_id or "",
            sub_task_id=sub_task_id or "",
        )

    async def _generate_session_title(self, session_id: str, user_message: str) -> None:
        """使用 LLM 生成会话标题

        Args:
            session_id: 会话 ID
            user_message: 用户的第一条消息
        """
        try:
            from langchain_core.prompts import PromptTemplate

            if not self.llm_provider:
                logger.warning(
                    "LLM Provider not configured, skipping title generation")
                return

            # 创建 LLM 实例（不绑定工具）
            llm = self.llm_provider.create_chat_model()

            # 构建提示词
            prompt = PromptTemplate.from_template(
                "请根据用户的消息内容，生成一个简洁的会话标题（不超过15个中文字符或30个英文字符）。\n"
                "要求：\n"
                "1. 准确概括用户的核心需求或意图\n"
                "2. 简洁明了，适合作为会话列表的显示标题\n"
                "3. 只返回标题文本，不要添加任何解释或其他内容\n\n"
                "用户消息：{message}\n\n"
                "标题："
            )

            # 调用 LLM
            # 限制输入长度
            response = await llm.ainvoke(prompt.format(message=user_message[:500]))

            # 提取标题（去除前后空白和可能的引号）
            title = response.content.strip().strip('"').strip("'")

            # 限制标题长度
            if len(title) > 30:
                title = title[:30].rstrip()

            # 更新会话标题
            session = await self.session_repo.get_by_id(session_id)
            if session and not session.title:  # 只在还没有标题时更新
                session.title = title
                await self.session_repo.update(session)
                logger.info("Generated session title: %s", title)

        except Exception as e:
            logger.exception("Failed to generate session title: %s", e)
            # 如果生成失败，使用默认的截取方式
            session = await self.session_repo.get_by_id(session_id)
            if session and not session.title:
                session.auto_title(user_message)
                await self.session_repo.update(session)

    async def _finalize_terminal_result(
        self,
        *,
        task: Task,
        session_id: str,
        result: Dict[str, Any],
        event_emitter: Optional[IEventEmitter] = None,
        persist_session_messages: bool = True,
    ) -> None:
        """处理终态结果

        Args:
            task: Task 实体
            session_id: Session ID
            result: LangGraph 执行结果
            event_emitter: 事件发射器（可选，默认使用 self.event_emitter）
        """
        emitter = event_emitter or self.event_emitter
        final_result = result.get("final_result")
        error = result.get("error")
        final_turn = result.get("current_turn", task.current_turn)
        previous_phase = result.get("phase", "thinking")

        all_tool_calls = []
        all_tool_results = []
        for msg in result.get("messages", []):
            tc = None
            if isinstance(msg, dict):
                tc = msg.get("tool_calls")
            elif hasattr(msg, "tool_calls"):
                tc = msg.tool_calls
            if tc:
                for t in tc:
                    if isinstance(t, dict):
                        all_tool_calls.append(
                            {"name": t.get("name", ""), "args": t.get(
                                "args", {}), "id": t.get("id", "")}
                        )
                    else:
                        all_tool_calls.append(
                            {
                                "name": getattr(t, "name", ""),
                                "args": getattr(t, "args", {}) or {},
                                "id": getattr(t, "id", ""),
                            }
                        )

        # 分离 clarify 输出与普通工具结果：
        # - clarify 的输出作为 assistant 正文呈现给用户，不进入 tool_results
        # - 其他工具正常收集到 all_tool_results
        clarify_outputs: list[str] = []
        for tool_call_id, tool_result in (result.get("tool_results") or {}).items():
            output = _tool_output_text(tool_result)
            if tool_result.get("tool_name") == "clarify":
                if output:
                    clarify_outputs.append(output)
                continue
            all_tool_results.append(
                {
                    "tool_name": tool_result.get("tool_name", ""),
                    "id": tool_call_id,
                    "status": tool_result.get("status", "success"),
                    "result": output,
                }
            )

        # 计算 assistant 正文：
        # 1. 如果有 clarify 输出，直接使用 clarify 输出（final_result 已包含 clarify 内容，避免重复）
        # 2. 否则用终态输出 (final_result 或 error)
        # 3. 最后回溯取最后一条非空消息内容
        if clarify_outputs:
            # clarify 输出已经通过 final_result 设置，直接使用 clarify_outputs 避免重复
            assistant_content = "\n\n".join(clarify_outputs)
        else:
            assistant_content = (
                final_result
                or error
                or _extract_last_message_content(result.get("messages", []))
            )

        assistant_msg: Optional[SessionMessage] = None
        if persist_session_messages:
            assistant_msg = SessionMessage(
                session_id=session_id,
                task_id=task.id,
                role=SessionMessageRole.ASSISTANT,
                content=assistant_content,
                tool_calls=all_tool_calls,
                tool_results=all_tool_results,
                status=MessageStatus.ERROR if error else MessageStatus.COMPLETED,
                error=error,
            )
            assistant_msg = await self.message_repo.add(assistant_msg)

        if self.task_repo:
            task.status = TaskStatus.FAILED if error else TaskStatus.COMPLETED
            task.current_turn = final_turn
            task.completed_at = datetime.now()
            task.result = final_result
            task.error = error
            await self.task_repo.update(task)

        if persist_session_messages:
            session = await self.session_repo.get_by_id(session_id)
            if session:
                session.update_metadata(assistant_content)
                await self.session_repo.update(session)

        await emitter.emit_phase_changed(
            task.id,
            "failed" if error else "complete",
            previous_phase,
            final_turn,
        )
        if assistant_msg is not None:
            await emitter.emit(
                task.id,
                "session:message:saved",
                _build_message_event_payload(assistant_msg),
            )
        if error:
            await emitter.emit(task.id, "task:failed", {"error": error})
        else:
            await emitter.emit(task.id, "task:completed", {"result": final_result})

    async def _run_agent_loop(
        self,
        agent_id: str,
        session_id: str,
        task: Task,
        content: str,
        model: Optional[str],
        max_turns: int,
        workspace: str,
        skill_ids: Optional[list[str]] = None,
        # Sub-agent 模式参数
        is_sub_agent: bool = False,
        parent_task_id: Optional[str] = None,
        sub_agent_description: Optional[str] = None,
        parent_system_prompt: Optional[str] = None,
        allowed_tools: Optional[list[str]] = None,
        persist_session_messages: bool = True,
    ) -> None:
        """后台 Agent Loop Runner"""
        effective_event_emitter = self._build_event_emitter(
            is_sub_agent=is_sub_agent,
            parent_task_id=parent_task_id,
            sub_task_id=task.id,
        )
        if model is None:
            from src.infrastructure.llm.config import LLMSettings
            model = LLMSettings().default_model

        try:
            # 步骤 A: 构建 system_prompt（使用 11 层 Prompt 架构）
            agent = await self.agent_repo.get_by_id(agent_id)
            if not agent:
                raise ValueError(f"Agent {agent_id} not found")

            # 使用新的 PromptAssembleService 组装 11 层 system_message
            template = PromptTemplate.from_agent(agent)
            assemble_service = PromptAssembleService()

            # 从 ToolRegistry 获取 ToolDef 列表（用于 Layer 5 工具描述）
            tool_defs = []
            if self.tool_registry:
                tool_defs = self.tool_registry.get_tool_defs()

            # 从 SkillRepository 获取选中的 SkillDef 列表（用于 Layer 8 注入）
            skill_defs = []
            if self.skill_repo and skill_ids:
                skill_defs = await self.skill_repo.get_by_ids(skill_ids)

            assembly_result = assemble_service.assemble(
                template=template,
                tools=tool_defs,  # 注入工具定义到 Layer 5
                skills=skill_defs,  # 注入选中的 Skills 到 Layer 8
                workspace=workspace,
                environment={
                    "platform": "darwin",
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "timezone": "Asia/Shanghai",
                },
                memory_enabled=bool(template.memory_md),
            )
            agent_system_prompt = assembly_result.system_message

            # 根据模式构建 system prompt
            system_prompt = self._build_system_prompt(
                is_sub_agent=is_sub_agent,
                parent_system_prompt=parent_system_prompt,
                sub_agent_description=sub_agent_description,
                agent_system_prompt=agent_system_prompt,
            )

            logger.info(
                "[Prompt Assembly] agent=%s | layers=%s | total_tokens=%d | static_prefix_tokens=%d",
                agent_id,
                assembly_result.layers,
                assembly_result.total_token_estimate,
                assembly_result.static_prefix_tokens,
            )

            # 步骤 B: 加载会话历史 → LangChain 消息格式
            # 注意：历史 AIMessage 不传 tool_calls，因为对应的 ToolMessage
            # 没有一并回放，传入会触发 LLM provider 报错（tool_call 无对应结果），
            # 同时也避免旧数据中 tool_calls 缺少 keyword-only 参数 `args` 时
            # AIMessage 构造抛出 `tool_call() missing 1 required keyword-only argument: 'args'`。
            history_messages = await self.message_repo.list_by_session(session_id, limit=20)
            messages = []
            for msg in history_messages:
                # 跳过当前这条用户消息（会在 initial_state 中作为 user_message 处理）
                if msg.role == SessionMessageRole.USER:
                    messages.append(HumanMessage(content=msg.content))
                elif msg.role == SessionMessageRole.ASSISTANT:
                    # 构建内容：保留原始内容 + 工具使用记录（去重）
                    content_parts = [msg.content or ""]
                    if msg.tool_calls:
                        # 提取工具名称并去重
                        tool_names = list(dict.fromkeys(
                            tc.get("name", "") for tc in msg.tool_calls if tc.get("name")
                        ))
                        if tool_names:
                            tools_summary = f"\n\n[Used Tools: {', '.join(tool_names)}]"
                            content_parts.append(tools_summary)

                    messages.append(AIMessage(content="".join(content_parts)))
                elif msg.role == SessionMessageRole.TOOL_SUMMARY:
                    messages.append(HumanMessage(
                        content=f"[Tool Results] {msg.content}"))

            # 步骤 C: 创建 LLM 实例 + 绑定工具
            # 根据模式构建工具注册表
            effective_tool_registry = self._build_tool_registry(
                is_sub_agent=is_sub_agent,
                allowed_tools=allowed_tools,
            )
            llm = self._build_llm(model, effective_tool_registry, agent_id)

            # 步骤 D: 构建初始 AgentState
            initial_state = {
                "messages": messages,
                "task_id": task.id,
                "workspace": workspace,
                "user_message": content,
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
                "route_hint": None,
                "observe_mode": None,
                "compression_strategy": None,
                "is_sub_agent": is_sub_agent,
                "parent_task_id": parent_task_id,
            }

            # 步骤 E: 编译并执行 LangGraph
            graph = AgentWorkflowBuilder().build()

            graph_config = {
                "configurable": {
                    "llm": llm,
                    "event_emitter": effective_event_emitter,
                    "event_service": effective_event_emitter,
                    "tool_registry": effective_tool_registry,
                    "agent_id": agent_id,
                    "llm_model": model,
                    "session_id": session_id,
                    # 注入 context 依赖，供工具使用
                    "send_message_use_case": self,
                    "task_repo": self.task_repo,
                    "parent_state": initial_state,
                    "parent_agent_id": agent_id,
                    "parent_session_id": session_id,
                    "parent_task_id": parent_task_id or task.id,
                }
            }

            await effective_event_emitter.emit(task.id, "task:started", {})

            result = await graph.ainvoke(initial_state, graph_config)

            await self._finalize_terminal_result(
                task=task,
                session_id=session_id,
                result=result,
                event_emitter=effective_event_emitter,
                persist_session_messages=persist_session_messages,
            )

        except asyncio.CancelledError:
            logger.info("Agent loop cancelled for task %s", task.id)
            if self.task_repo:
                task.status = TaskStatus.CANCELLED
                task.completed_at = datetime.now()
                task.error = "cancelled"
                await self.task_repo.update(task)
            if effective_event_emitter:
                await effective_event_emitter.emit_phase_changed(
                    task.id,
                    "cancelled",
                    "thinking",
                    task.current_turn,
                )
                await effective_event_emitter.emit(
                    task.id, "task:cancelled", {}
                )
        except Exception as e:
            logger.exception("Agent loop failed for task %s: %s", task.id, e)
            if self.task_repo:
                task.status = TaskStatus.FAILED
                task.completed_at = datetime.now()
                task.error = str(e)
                await self.task_repo.update(task)
            if effective_event_emitter:
                await effective_event_emitter.emit_phase_changed(
                    task.id,
                    "failed",
                    "thinking",
                    task.current_turn,
                )
                await effective_event_emitter.emit(
                    task.id, "task:failed", {"error": str(e)}
                )
