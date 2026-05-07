"""基础设施层 - Agent 节点基类

提供统一的节点执行框架,处理日志、事件发射、异常处理等切面逻辑。
所有 Agent 节点应继承此基类,只需关注核心业务逻辑。
"""

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from langgraph.types import RunnableConfig

from src.domain.entities.agent_state import AgentState

logger = logging.getLogger(__name__)


@dataclass
class NodeContext:
    """节点执行上下文 - 封装通用配置信息"""
    agent_id: str
    task_id: str
    current_turn: int
    event_emitter: Any
    previous_phase: str


class BaseNode(ABC):
    """Agent 节点基类 - 统一处理日志、事件、异常等切面逻辑

    使用模板方法模式定义节点执行流程:
    1. 提取通用上下文
    2. 记录入口日志
    3. 发射 phase 变更事件
    4. 执行子类核心逻辑
    5. 记录完成日志
    6. 异常处理(如发生)

    子类只需实现:
    - node_name: 节点名称
    - execute: 核心业务逻辑
    - default_phase (可选): 默认 phase 名称
    """

    @property
    @abstractmethod
    def node_name(self) -> str:
        """节点名称(用于日志和事件)"""
        pass

    @property
    def default_phase(self) -> str | None:
        """默认 phase 名称(用于事件发射,返回 None 则不发射)"""
        return None

    async def __call__(self, state: AgentState, config: RunnableConfig) -> dict:
        """LangGraph 调用入口(模板方法模式)

        Args:
            state: 当前 Agent 状态
            config: LangGraph 配置

        Returns:
            状态更新字典
        """
        # 记录开始时间(用于性能监控)
        start_time = time.time()

        # 1. 提取通用上下文
        context = self._extract_context(state, config)

        # 2. 记录入口日志
        self._log_start(context, state)

        # 3. 发射 phase 变更事件
        await self._emit_phase_change(context, state)

        try:
            # 4. 执行子类核心逻辑
            result = await self.execute(state, config, context)

            # 5. 记录完成日志
            duration = time.time() - start_time
            self._log_complete(context, result, duration)

            return result

        except Exception as e:
            # 6. 异常处理与日志
            duration = time.time() - start_time
            self._log_error(context, e, duration)
            return await self._handle_error(context, e)

    @abstractmethod
    async def execute(self, state: AgentState, config: RunnableConfig, context: NodeContext) -> dict:
        """子类实现的核心业务逻辑

        Args:
            state: 当前 Agent 状态
            config: LangGraph 配置
            context: 节点执行上下文

        Returns:
            状态更新字典
        """
        pass

    def _extract_context(self, state: AgentState, config: RunnableConfig) -> NodeContext:
        """提取通用上下文信息

        Args:
            state: 当前 Agent 状态
            config: LangGraph 配置

        Returns:
            NodeContext 实例
        """
        return NodeContext(
            agent_id=config.get("configurable", {}).get("agent_id", "unknown"),
            task_id=state.get("task_id", ""),
            current_turn=state.get("current_turn", 0),
            event_emitter=self._get_event_emitter(config),
            previous_phase=state.get("phase", "idle"),
        )

    def _get_event_emitter(self, config: RunnableConfig) -> Any:
        """从配置中获取事件发射器

        Args:
            config: LangGraph 配置

        Returns:
            事件发射器实例
        """
        return (config.get("configurable") or {}).get("event_emitter") or (
            config.get("configurable") or {}
        ).get("event_service")

    def _exhausted_turn_budget(self, state: AgentState) -> bool:
        """检查是否已耗尽 turn 预算

        Args:
            state: 当前 Agent 状态

        Returns:
            是否已耗尽 turn 预算
        """
        return state.get("current_turn", 0) >= state.get("max_turns", 100)

    def _log_start(self, context: NodeContext, state: AgentState):
        """统一的入口日志

        Args:
            context: 节点执行上下文
            state: 当前 Agent 状态
        """
        logger.info(
            "[NODE:%s] START | agent_id=%s | task_id=%s | turn=%d | phase=%s",
            self.node_name,
            context.agent_id,
            context.task_id,
            context.current_turn,
            context.previous_phase
        )

    def _log_complete(self, context: NodeContext, result: dict, duration: float):
        """统一的完成日志

        Args:
            context: 节点执行上下文
            result: 执行结果
            duration: 执行耗时(秒)
        """
        logger.info(
            "[NODE:%s] COMPLETE | task_id=%s | turn=%d | phase=%s | duration=%.2fs",
            self.node_name,
            context.task_id,
            context.current_turn,
            result.get("phase", "unknown"),
            duration
        )

    def _log_error(self, context: NodeContext, error: Exception, duration: float):
        """统一的错误日志

        Args:
            context: 节点执行上下文
            error: 异常对象
            duration: 执行耗时(秒)
        """
        logger.error(
            "[NODE:%s] ERROR | task_id=%s | turn=%d | error=%s | duration=%.2fs",
            self.node_name,
            context.task_id,
            context.current_turn,
            str(error),
            duration
        )

    async def _emit_phase_change(self, context: NodeContext, state: AgentState):
        """统一的 phase 变更事件发射

        Args:
            context: 节点执行上下文
            state: 当前 Agent 状态
        """
        if context.event_emitter and self.default_phase:
            try:
                await context.event_emitter.emit_phase_changed(
                    context.task_id,
                    self.default_phase,
                    context.previous_phase,
                    context.current_turn,
                )
            except Exception as e:
                logger.warning(
                    "[NODE:%s] PHASE_EVENT_ERROR | task_id=%s | error=%s",
                    self.node_name,
                    context.task_id,
                    str(e)
                )

    async def _handle_error(self, context: NodeContext, error: Exception) -> dict:
        """统一的错误处理(可被子类覆盖)

        Args:
            context: 节点执行上下文
            error: 异常对象

        Returns:
            错误状态更新字典
        """
        return {
            "error": str(error),
            "should_end": True,
            "phase": "error",
        }
