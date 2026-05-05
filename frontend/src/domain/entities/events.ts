/**
 * 领域层 - SSE Agent 事件类型定义
 *
 * 与后端 backend/src/infrastructure/agent/nodes/*、send_message.py 发射的事件保持一致。
 * 注意：后端在 SSE 协议层将事件名中的冒号(:) 转换为连字符(-)，前端接收后会转回冒号格式。
 */

import type { SessionMessage } from './session';
import type { AgentPhase } from './task';

/** 所有事件 payload 都包含的基础字段 */
export interface BaseEventPayload {
  taskId: string;
}

/** task-started 事件 */
export type TaskStartedPayload = BaseEventPayload;

/** task-completed 事件 */
export interface TaskCompletedPayload extends BaseEventPayload {
  result?: string;
}

/** task-failed 事件 */
export interface TaskFailedPayload extends BaseEventPayload {
  error: string;
}

/** task-cancelled 事件 */
export type TaskCancelledPayload = BaseEventPayload;

/** task-paused 事件 */
export interface TaskPausedPayload extends BaseEventPayload {
  reason: string;
}

/** task-resumed 事件 */
export type TaskResumedPayload = BaseEventPayload;

/** phase-changed 事件 */
export interface PhaseChangedPayload extends BaseEventPayload {
  phase: AgentPhase | string;
  previousPhase: AgentPhase | string;
  turn: number;
}

/** llm-chunk 事件（流式增量文本） */
export interface LLMChunkPayload extends BaseEventPayload {
  turn: number;
  text: string;
  delta: boolean;
}

/** llm-complete 事件 */
export interface LLMCompletePayload extends BaseEventPayload {
  turn: number;
  fullText: string;
  toolCalls: Array<{
    id: string;
    name: string;
    args: Record<string, unknown>;
  }>;
}

/** tool-call 事件 */
export interface ToolCallPayload extends BaseEventPayload {
  toolCallId: string;
  toolName: string;
  input: Record<string, unknown>;
}

/** tool-result 事件 */
export interface ToolResultPayload extends BaseEventPayload {
  toolCallId: string;
  toolName: string;
  status: 'success' | 'error' | string;
  output?: string;
  error?: string;
  metadata?: Record<string, unknown>;
}

/** context-compacting 事件 */
export interface ContextCompactingPayload extends BaseEventPayload {
  beforeTokens: number;
  afterTokens: number;
}

/** loop-detected 事件 */
export interface LoopDetectedPayload extends BaseEventPayload {
  loopType: string;
  count: number;
  action: string;
}

/** stuck-detected 事件 */
export interface StuckDetectedPayload extends BaseEventPayload {
  stuckType: string;
  count: number;
  action: string;
}

/** step-created 事件（多步骤任务） */
export interface StepCreatedPayload extends BaseEventPayload {
  plan_id: string;
  goal?: string;
  execution_order?: unknown[];
}

/** step-started 事件（多步骤任务） */
export interface StepStartedPayload extends BaseEventPayload {
  step_id: number;
  description?: string;
}

/** step-completed 事件（多步骤任务） */
export interface StepCompletedPayload extends BaseEventPayload {
  step_id: number;
  status: 'completed' | 'failed' | string;
  result?: string | null;
  error?: string | null;
  sub_agent_task_id?: string | null;
}

/** step-parallel-group-started 事件（多步骤任务） */
export interface StepParallelGroupStartedPayload extends BaseEventPayload {
  step_ids: number[];
}

/** step-parallel-group-completed 事件（多步骤任务） */
export interface StepParallelGroupCompletedPayload extends BaseEventPayload {
  step_ids: number[];
  results?: Record<
    string,
    {
      status: 'completed' | 'failed' | string;
      result?: string | null;
      error?: string | null;
      sub_agent_task_id?: string | null;
    }
  >;
}

/** step-all-completed 事件（多步骤任务全部完成） */
export interface StepAllCompletedPayload extends BaseEventPayload {
  plan_id: string;
  summary?: string;
  step_results?: Record<
    string,
    {
      status: 'completed' | 'failed' | string;
      result?: string | null;
      error?: string | null;
      sub_agent_task_id?: string | null;
    }
  >;
}

/** sub-agent 事件 */
export interface SubAgentPayload extends BaseEventPayload {
  sub_task_id: string;
  step_id?: number;
  description?: string;
  status?: string;
  result?: string | null;
  error?: string | null;
}

/** session-message-saved 事件（最终落库消息） */
export interface SessionMessageSavedPayload extends BaseEventPayload {
  message: SessionMessage;
}

/**
 * 内部事件名（冒号分隔）到 payload 类型的映射。
 * 供 AgentEventStream 的强类型监听使用。
 */
export interface AgentEventMap {
  'task:started': TaskStartedPayload;
  'task:completed': TaskCompletedPayload;
  'task:failed': TaskFailedPayload;
  'task:cancelled': TaskCancelledPayload;
  'task:paused': TaskPausedPayload;
  'task:resumed': TaskResumedPayload;
  'phase:changed': PhaseChangedPayload;
  'llm:chunk': LLMChunkPayload;
  'llm:complete': LLMCompletePayload;
  'tool:call': ToolCallPayload;
  'tool:result': ToolResultPayload;
  'context:compacting': ContextCompactingPayload;
  'loop:detected': LoopDetectedPayload;
  'stuck:detected': StuckDetectedPayload;
  'step:created': StepCreatedPayload;
  'step:started': StepStartedPayload;
  'step:completed': StepCompletedPayload;
  'step:parallel_group_started': StepParallelGroupStartedPayload;
  'step:parallel_group_completed': StepParallelGroupCompletedPayload;
  'step:all_completed': StepAllCompletedPayload;
  'sub_agent:started': SubAgentPayload;
  'sub_agent:completed': SubAgentPayload;
  'sub_agent:failed': SubAgentPayload;
  'session:message:saved': SessionMessageSavedPayload;
}

/** 所有合法的事件名 */
export type AgentEventName = keyof AgentEventMap;

/**
 * SSE 协议层事件名（连字符）列表 —— 与后端 emit 保持一致。
 * 注意：session-message-saved 在协议层仅用单连字符替换第一个冒号，
 * 因此这里列出实际由后端发出的 SSE event 字段。
 */
export const SSE_EVENT_TYPES: readonly string[] = [
  'task-started',
  'task-completed',
  'task-failed',
  'task-cancelled',
  'task-paused',
  'task-resumed',
  'phase-changed',
  'llm-chunk',
  'llm-complete',
  'tool-call',
  'tool-result',
  'context-compacting',
  'loop-detected',
  'stuck-detected',
  'step-created',
  'step-step_started',
  'step-step_completed',
  'step-parallel_group_started',
  'step-parallel_group_completed',
  'step-all_completed',
  'sub_agent-started',
  'sub_agent-completed',
  'sub_agent-failed',
  'session-message-saved',
] as const;
