"""领域层 — Agent SSE 事件类型枚举

所有 Agent Loop 发射的事件类型统一在此定义。
后端 emit 时使用此枚举值；前端 `events.ts` 中 `AgentEventMap` 的 key 与此保持一致。
SSE 传输层会自动将冒号(:)转为连字符(-)。
"""

from enum import Enum


class AgentEventType(str, Enum):
    """Agent 事件类型枚举

    命名规范: `命名空间:动作`，如 `task:started`、`llm:chunk`
    """

    # ── Task 生命周期 ──
    TASK_STARTED = "task:started"
    TASK_COMPLETED = "task:completed"
    TASK_FAILED = "task:failed"
    TASK_CANCELLED = "task:cancelled"
    TASK_PAUSED = "task:paused"
    TASK_RESUMED = "task:resumed"

    # ── 阶段变更 ──
    PHASE_CHANGED = "phase:changed"

    # ── LLM 流式 ──
    LLM_CHUNK = "llm:chunk"
    LLM_COMPLETE = "llm:complete"
    THINKING_CHUNK = "thinking:chunk"

    # ── 工具调用 ──
    TOOL_CALL = "tool:call"
    TOOL_RESULT = "tool:result"

    # ── 上下文 ──
    CONTEXT_COMPACTING = "context:compacting"

    # ── 观测/检测 ──
    LOOP_DETECTED = "loop:detected"

    # ── 多步骤任务 ──
    STEP_CREATED = "step:created"
    STEP_STARTED = "step:started"
    STEP_COMPLETED = "step:completed"
    STEP_PARALLEL_GROUP_STARTED = "step:parallel_group_started"
    STEP_PARALLEL_GROUP_COMPLETED = "step:parallel_group_completed"
    STEP_ALL_COMPLETED = "step:all_completed"

    # ── Sub-Agent ──
    SUB_AGENT_STARTED = "sub_agent:started"
    SUB_AGENT_COMPLETED = "sub_agent:completed"
    SUB_AGENT_FAILED = "sub_agent:failed"

    # ── 会话 ──
    SESSION_MESSAGE_SAVED = "session:message:saved"
