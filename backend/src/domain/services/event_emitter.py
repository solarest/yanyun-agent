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


class ProxyEventEmitter(IEventEmitter):
    """代理事件发射器 - 用于转发 sub-agent 事件到父 stream

    将所有事件转发到父 event_emitter，并在 payload 中自动添加 sub_task_id 字段。
    这是一个装饰器模式的实现，用于事件转发和增强。
    """

    def __init__(
        self,
        parent_emitter: IEventEmitter,
        parent_task_id: str,
        sub_task_id: str,
    ):
        """初始化代理发射器

        Args:
            parent_emitter: 父事件发射器
            parent_task_id: 父 task ID，sub-agent 事件会写入这个事件流
            sub_task_id: sub-task ID，会添加到所有事件的 payload 中
        """
        self._parent_emitter = parent_emitter
        self._parent_task_id = parent_task_id
        self._sub_task_id = sub_task_id

    async def emit(self, task_id: str, event_type: str, payload: dict[str, Any]) -> None:
        """转发事件到父 stream，添加 sub_task_id"""
        payload = {**payload, "sub_task_id": self._sub_task_id}
        await self._parent_emitter.emit(self._parent_task_id, event_type, payload)

    async def emit_phase_changed(
        self,
        task_id: str,
        new_phase: str,
        previous_phase: str,
        turn: int,
    ) -> None:
        """转发阶段变更事件"""
        await self._parent_emitter.emit(
            self._parent_task_id,
            "phase:changed",
            {
                "phase": new_phase,
                "previousPhase": previous_phase,
                "turn": turn,
                "sub_task_id": self._sub_task_id,
            },
        )

    async def emit_llm_chunk(
        self,
        task_id: str,
        turn: int,
        text: str,
    ) -> None:
        """转发 LLM 流式片段"""
        await self._parent_emitter.emit(
            self._parent_task_id,
            "llm:chunk",
            {
                "turn": turn,
                "text": text,
                "delta": True,
                "sub_task_id": self._sub_task_id,
            },
        )

    async def emit_thinking_chunk(
        self,
        task_id: str,
        turn: int,
        text: str,
    ) -> None:
        """转发深度思考片段"""
        await self._parent_emitter.emit(
            self._parent_task_id,
            "thinking:chunk",
            {
                "turn": turn,
                "text": text,
                "delta": True,
                "sub_task_id": self._sub_task_id,
            },
        )

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
