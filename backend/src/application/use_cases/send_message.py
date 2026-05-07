"""应用层 - SendMessage 用例

核心编排用例：用户发送消息 → 创建 Task → 异步启动 Agent Loop。
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from langchain_core.messages import AIMessage, HumanMessage

from src.application.use_cases.agent_workflow import AgentWorkflowBuilder
from src.domain.entities.session_message import (
    MessageStatus,
    SessionMessage,
    SessionMessageRole,
)
from src.domain.entities.task import Task, TaskConfig, TaskStatus
from src.domain.repositories.agent_repository import IAgentRepository
from src.domain.repositories.session_message_repository import (
    ISessionMessageRepository,
)
from src.domain.repositories.session_repository import ISessionRepository
from src.domain.repositories.skill_repository import ISkillRepository
from src.domain.repositories.task_repository import ITaskRepository
from src.domain.services import IEventEmitter
from src.domain.entities.prompt_template import PromptTemplate
from src.domain.services.prompt_assemble_service import PromptAssembleService
from src.infrastructure.llm.model_factory import create_chat_model
from src.infrastructure.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


def _tool_defs_to_openai_functions(tool_registry: ToolRegistry) -> list:
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
        tool_registry: Optional[ToolRegistry] = None,
        skill_repo: Optional[ISkillRepository] = None,
        running_tasks: Optional[dict[str, asyncio.Task]] = None,
    ):
        self.agent_repo = agent_repo
        self.session_repo = session_repo
        self.message_repo = message_repo
        self.task_repo = task_repo
        self.event_emitter = event_emitter
        self.tool_registry = tool_registry
        self.skill_repo = skill_repo
        self.running_tasks = running_tasks if running_tasks is not None else {}

    async def execute(
        self,
        agent_id: str,
        session_id: str,
        content: str,
        model: Optional[str] = None,
        max_turns: int = 100,
        workspace: str = "/tmp/agent-workspace",
        skill_ids: Optional[list[str]] = None,
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

        Returns:
            {"user_message": SessionMessage, "task_id": str}
        """
        # 1. 保存用户消息
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
        if self.task_repo:
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
                    model=model,
                    max_turns=max_turns,
                    workspace=workspace,
                    skill_ids=skill_ids or [],
                )
            )
            asyncio_task.add_done_callback(
                lambda t: logger.info("Agent loop task %s finished", task.id)
            )

        return {
            "user_message": user_msg,
            "task_id": task.id,
            "asyncio_task": asyncio_task if (self.event_emitter and self.tool_registry) else None,
        }

    def _build_llm(self, model: Optional[str], tool_registry: Optional[ToolRegistry], agent_id: str):
        llm = create_chat_model(model=model or None)
        if tool_registry and tool_registry.tool_count > 0:
            tool_schemas = _tool_defs_to_openai_functions(tool_registry)
            llm = llm.bind_tools(tool_schemas)
            logger.info("binding-tools agent %s Tool schemas: %s",
                        agent_id, tool_schemas)
        return llm

    def _build_graph_config(
        self,
        llm,
        tool_registry: Optional[ToolRegistry],
        agent_id: str,
        model: Optional[str],
    ) -> Dict[str, Any]:
        return {
            "configurable": {
                "llm": llm,
                "event_emitter": self.event_emitter,
                "event_service": self.event_emitter,
                "tool_registry": tool_registry,
                "agent_id": agent_id,
                "llm_model": model,
            }
        }

    async def _generate_session_title(self, session_id: str, user_message: str) -> None:
        """使用 LLM 生成会话标题

        Args:
            session_id: 会话 ID
            user_message: 用户的第一条消息
        """
        try:
            from langchain_core.prompts import PromptTemplate
            from src.infrastructure.llm.model_factory import create_chat_model

            # 创建 LLM 实例（不绑定工具）
            llm = create_chat_model()

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
    ) -> None:
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
        # 1. 优先用终态输出 (final_result 或 error)
        # 2. 否则回溯取最后一条非空消息内容
        # 3. 最后将多条 clarify 问题（如有）以空行分隔追加到正文末尾，供前端解析
        assistant_content = (
            final_result
            or error
            or _extract_last_message_content(result.get("messages", []))
        )
        if clarify_outputs:
            clarify_block = "\n\n".join(clarify_outputs)
            assistant_content = (
                f"{assistant_content}\n\n{clarify_block}"
                if assistant_content
                else clarify_block
            )

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

        session = await self.session_repo.get_by_id(session_id)
        if session:
            session.update_metadata(assistant_content)
            await self.session_repo.update(session)

        await self.event_emitter.emit_phase_changed(
            task.id,
            "failed" if error else "complete",
            previous_phase,
            final_turn,
        )
        await self.event_emitter.emit(
            task.id,
            "session:message:saved",
            _build_message_event_payload(assistant_msg),
        )
        if error:
            await self.event_emitter.emit(task.id, "task:failed", {"error": error})
        else:
            await self.event_emitter.emit(task.id, "task:completed", {"result": final_result})

    async def _run_agent_loop(
        self,
        agent_id: str,
        session_id: str,
        task: Task,
        content: str,
        model: str,
        max_turns: int,
        workspace: str,
        skill_ids: Optional[list[str]] = None,
    ) -> None:
        """后台 Agent Loop Runner"""
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
            system_prompt = assembly_result.system_message

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
            llm = self._build_llm(model, self.tool_registry, agent_id)

            # 步骤 D: 构建初始 AgentState
            initial_state = {
                "messages": messages,
                "task_id": task.id,
                "workspace": workspace,
                "user_message": content,
                "task_start_message_count": len(messages),
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
                "is_sub_agent": False,
                "parent_task_id": None,
            }

            # 步骤 E: 编译并执行 LangGraph
            graph = AgentWorkflowBuilder().build()
            graph_config = self._build_graph_config(
                llm, self.tool_registry, agent_id, model)

            await self.event_emitter.emit(task.id, "task:started", {})

            result = await graph.ainvoke(initial_state, graph_config)

            await self._finalize_terminal_result(
                task=task,
                session_id=session_id,
                result=result,
            )

        except asyncio.CancelledError:
            logger.info("Agent loop cancelled for task %s", task.id)
            if self.task_repo:
                task.status = TaskStatus.CANCELLED
                task.completed_at = datetime.now()
                task.error = "cancelled"
                await self.task_repo.update(task)
            if self.event_emitter:
                await self.event_emitter.emit_phase_changed(
                    task.id,
                    "cancelled",
                    "thinking",
                    task.current_turn,
                )
                await self.event_emitter.emit(
                    task.id, "task:cancelled", {}
                )
        except Exception as e:
            logger.exception("Agent loop failed for task %s: %s", task.id, e)
            if self.task_repo:
                task.status = TaskStatus.FAILED
                task.completed_at = datetime.now()
                task.error = str(e)
                await self.task_repo.update(task)
            if self.event_emitter:
                await self.event_emitter.emit_phase_changed(
                    task.id,
                    "failed",
                    "thinking",
                    task.current_turn,
                )
                await self.event_emitter.emit(
                    task.id, "task:failed", {"error": str(e)}
                )
