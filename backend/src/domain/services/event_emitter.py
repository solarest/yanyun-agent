"""领域层 - 事件发射 SPI。"""

from abc import ABC, abstractmethod
from typing import Any, Dict


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
