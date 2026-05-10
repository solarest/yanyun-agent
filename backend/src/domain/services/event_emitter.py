"""领域层 - 事件发射 SPI。"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict

logger = logging.getLogger(__name__)


class IEventEmitter(ABC):
    """Agent Loop 事件发射器接口。"""

    @abstractmethod
    async def emit(self, task_id: str, event_type: str, payload: Dict[str, Any]) -> None:
        """发射一个事件。"""
        pass

    @abstractmethod
    async def emit_phase_changed(
        self,
        task_id: str,
        new_phase: str,
        previous_phase: str,
        turn: int,
    ) -> None:
        """发射阶段变更事件。"""
        pass

    @abstractmethod
    async def emit_llm_chunk(
        self,
        task_id: str,
        turn: int,
        text: str,
    ) -> None:
        """发射 LLM 流式增量文本。"""
        pass

    @abstractmethod
    async def emit_thinking_chunk(
        self,
        task_id: str,
        turn: int,
        text: str,
    ) -> None:
        """发射 LLM 深度思考流式增量文本。"""
        pass

    async def emit_safe(self, task_id: str, event_type: str, payload: Dict[str, Any]) -> None:
        """安全地发射事件，忽略异常。

        Args:
            task_id: 任务 ID
            event_type: 事件类型
            payload: 事件负载
        """
        try:
            await self.emit(task_id, event_type, payload)
        except Exception as exc:
            logger.warning("event emit failed: %s", exc)

    async def emit_phase_changed_safe(
        self,
        task_id: str,
        new_phase: str,
        previous_phase: str,
        turn: int,
    ) -> None:
        """安全地发射阶段变更事件，忽略异常。

        Args:
            task_id: 任务 ID
            new_phase: 新阶段
            previous_phase: 之前阶段
            turn: 当前轮次
        """
        try:
            await self.emit_phase_changed(task_id, new_phase, previous_phase, turn)
        except Exception as exc:
            logger.warning("phase event failed: %s", exc)
