"""AgentState 分组访问器 — 按职责提供结构化读写接口

将 AgentState 的 32 个平铺字段分为 4 个职责组:
- ControlFields: 控制流 (current_turn, max_turns, phase, should_end, is_complete)
- ContextFields: 上下文管理 (max_tokens, estimate, baseline, compaction, emergency)
- ToolFields: 工具执行 (pending, results, awaiting_input, executed_ids, final_result)
- TaskFields: 任务上下文 (task_id, workspace, user_message, model, system_prompt, sub-agent)

每个 dataclass 提供:
- from_state(state) -> Self: 从 AgentState 读取
- to_update() -> dict: 生成 LangGraph state update
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.domain.aggregates.agent.agent_state import AgentState


@dataclass
class ControlFields:
    """由 llm_call, tool_execute 写入的控制流字段"""

    current_turn: int = 0
    max_turns: int = 100
    phase: str = "idle"
    should_end: bool = False
    is_complete: bool = False

    @classmethod
    def from_state(cls, state: AgentState) -> "ControlFields":
        return cls(
            current_turn=state.get("current_turn", 0),
            max_turns=state.get("max_turns", 100),
            phase=state.get("phase", "idle"),
            should_end=state.get("should_end", False),
            is_complete=state.get("is_complete", False),
        )

    def to_update(self) -> dict:
        return {
            "current_turn": self.current_turn,
            "max_turns": self.max_turns,
            "phase": self.phase,
            "should_end": self.should_end,
            "is_complete": self.is_complete,
        }


@dataclass
class ContextFields:
    """由 context_compact, llm_call 写入的上下文管理字段"""

    max_tokens: int = 128_000
    estimate: int = 0
    baseline: int | None = None
    baseline_count: int = 0
    compaction_attempts: int = 0
    emergency_requested: bool = False
    last_strategy: str | None = None

    @classmethod
    def from_state(cls, state: AgentState) -> "ContextFields":
        return cls(
            max_tokens=state.get("max_context_tokens", 128_000),
            estimate=state.get("context_token_estimate", 0),
            baseline=state.get("context_token_baseline"),
            baseline_count=state.get("context_token_baseline_message_count", 0),
            compaction_attempts=state.get("context_compaction_attempts", 0),
            emergency_requested=state.get("emergency_compact_requested", False),
            last_strategy=state.get("last_context_strategy"),
        )

    def to_update(self) -> dict:
        return {
            "max_context_tokens": self.max_tokens,
            "context_token_estimate": self.estimate,
            "context_token_baseline": self.baseline,
            "context_token_baseline_message_count": self.baseline_count,
            "context_compaction_attempts": self.compaction_attempts,
            "emergency_compact_requested": self.emergency_requested,
            "last_context_strategy": self.last_strategy,
        }


@dataclass
class ToolFields:
    """由 tool_execute_node 写入的工具执行状态"""

    pending: list[dict[str, Any]] = field(default_factory=list)
    results: dict[str, dict[str, Any]] = field(default_factory=dict)
    awaiting_input: bool = False
    last_executed_ids: list[str] = field(default_factory=list)
    final_result: str | None = None

    @classmethod
    def from_state(cls, state: AgentState) -> "ToolFields":
        return cls(
            pending=list(state.get("pending_tool_calls", [])),
            results=dict(state.get("tool_results", {})),
            awaiting_input=state.get("awaiting_user_input", False),
            last_executed_ids=list(state.get("last_executed_tool_call_ids", [])),
            final_result=state.get("final_result"),
        )

    def to_update(self) -> dict:
        return {
            "pending_tool_calls": self.pending,
            "tool_results": self.results,
            "awaiting_user_input": self.awaiting_input,
            "last_executed_tool_call_ids": self.last_executed_ids,
            "final_result": self.final_result,
        }


@dataclass
class TaskFields:
    """只读任务上下文字段（主要在 _build_initial_state 中使用）"""

    task_id: str = ""
    workspace: str = ""
    user_message: str = ""
    task_start_message_count: int = 0
    model: str = ""
    system_prompt: str = ""
    is_sub_agent: bool = False
    parent_task_id: str | None = None

    @classmethod
    def from_state(cls, state: AgentState) -> "TaskFields":
        return cls(
            task_id=state.get("task_id", ""),
            workspace=state.get("workspace", ""),
            user_message=state.get("user_message", ""),
            task_start_message_count=state.get("task_start_message_count", 0),
            model=state.get("model", ""),
            system_prompt=state.get("system_prompt", ""),
            is_sub_agent=state.get("is_sub_agent", False),
            parent_task_id=state.get("parent_task_id"),
        )

    def to_update(self) -> dict:
        return {
            "task_id": self.task_id,
            "workspace": self.workspace,
            "user_message": self.user_message,
            "task_start_message_count": self.task_start_message_count,
            "model": self.model,
            "system_prompt": self.system_prompt,
            "is_sub_agent": self.is_sub_agent,
            "parent_task_id": self.parent_task_id,
        }
