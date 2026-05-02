/**
 * 应用层 - Chat 聊天 Hook
 *
 * 编排发送消息 → SSE 订阅 → 实时更新消息列表的完整流程。
 */
import { useState, useCallback, useRef, useEffect } from 'react';
import { sessionApi } from '@infrastructure/api/sessionApi';
import { taskApi } from '@infrastructure/api/taskApi';
import { AgentEventStream } from '@infrastructure/api/eventStream';
import type { SessionMessage, SendMessageRequest } from '@domain/entities/session';
import type { AgentPhase } from '@domain/entities/task';

export type PlanStepStatus = 'pending' | 'running' | 'completed' | 'failed';
export type PlanStatus = 'planning' | 'executing' | 'completed' | 'failed';

export interface PlanStepProgress {
  id: number;
  description: string;
  status: PlanStepStatus;
  result?: string | null;
  error?: string | null;
}

export interface PlanProgress {
  goal: string;
  steps: PlanStepProgress[];
  status: PlanStatus;
  executionOrder?: unknown[];
}

export interface ChatState {
  isSending: boolean;
  isStreaming: boolean;
  streamingContent: string;
  currentPhase: AgentPhase;
  currentTaskId: string | null;
  error: string | null;
  currentPlan: PlanProgress | null;
}

interface UseChatOptions {
  agentId: string;
  sessionId: string | null;
  onMessageSaved?: (msg: SessionMessage) => void;
  onAppendMessage?: (msg: SessionMessage) => void;
  onUpdateLastAssistant?: (updater: (msg: SessionMessage) => SessionMessage) => void;
}

const INITIAL_STATE: ChatState = {
  isSending: false,
  isStreaming: false,
  streamingContent: '',
  currentPhase: 'idle',
  currentTaskId: null,
  error: null,
  currentPlan: null,
};

const PLAN_TOOL_NAMES = new Set(['plan', 'plan_execute']);

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const toStringValue = (value: unknown): string =>
  typeof value === 'string' ? value : value == null ? '' : String(value);

const toNumberValue = (value: unknown, fallback: number): number => {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
};

const normalizePlanSteps = (rawSteps: unknown): PlanStepProgress[] => {
  if (!Array.isArray(rawSteps)) return [];

  return rawSteps.map((step, index) => {
    if (isRecord(step)) {
      return {
        id: toNumberValue(step.id, index + 1),
        description: toStringValue(step.description || step.title || step.name),
        status: 'pending',
        result: null,
        error: null,
      };
    }

    return {
      id: index + 1,
      description: toStringValue(step),
      status: 'pending',
      result: null,
      error: null,
    };
  });
};

const buildPlanFromToolInput = (
  toolName: string,
  input: Record<string, unknown>,
  previousPlan: PlanProgress | null,
): PlanProgress | null => {
  if (!PLAN_TOOL_NAMES.has(toolName)) return null;

  const incomingSteps = normalizePlanSteps(input.steps);
  const previousSteps = new Map(previousPlan?.steps.map((step) => [step.id, step]));
  const steps = incomingSteps.map((step) => ({
    ...step,
    status: previousSteps.get(step.id)?.status || step.status,
    result: previousSteps.get(step.id)?.result || step.result,
    error: previousSteps.get(step.id)?.error || step.error,
  }));

  return {
    goal: toStringValue(input.goal) || previousPlan?.goal || 'Plan',
    steps,
    status: 'planning',
    executionOrder: Array.isArray(input.execution_order)
      ? input.execution_order
      : previousPlan?.executionOrder,
  };
};

const ensurePlan = (plan: PlanProgress | null): PlanProgress => ({
  goal: plan?.goal || 'Plan',
  steps: plan?.steps || [],
  status: plan?.status || 'planning',
  executionOrder: plan?.executionOrder,
});

const updatePlanStep = (
  plan: PlanProgress | null,
  stepId: number,
  updater: (step: PlanStepProgress) => PlanStepProgress,
  description?: string,
): PlanProgress => {
  const currentPlan = ensurePlan(plan);
  const stepIndex = currentPlan.steps.findIndex((step) => step.id === stepId);

  if (stepIndex === -1) {
    return {
      ...currentPlan,
      steps: [
        ...currentPlan.steps,
        updater({
          id: stepId,
          description: description || `Step ${stepId}`,
          status: 'pending',
          result: null,
          error: null,
        }),
      ].sort((a, b) => a.id - b.id),
    };
  }

  return {
    ...currentPlan,
    steps: currentPlan.steps.map((step) =>
      step.id === stepId
        ? updater({
            ...step,
            description: description || step.description,
          })
        : step,
    ),
  };
};

export const useChat = ({
  agentId,
  sessionId,
  onMessageSaved,
  onAppendMessage,
  onUpdateLastAssistant,
}: UseChatOptions) => {
  const [state, setState] = useState<ChatState>(INITIAL_STATE);

  const streamRef = useRef<AgentEventStream | null>(null);

  const disconnectStream = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.disconnect();
      streamRef.current = null;
    }
  }, []);

  /**
   * 发送消息
   */
  const sendMessage = useCallback(
    async (content: string, options?: Partial<SendMessageRequest>) => {
      if (!sessionId || !agentId || !content.trim()) return;

      setState((prev) => ({
        ...prev,
        isSending: true,
        error: null,
        streamingContent: '',
        currentPhase: 'idle',
        currentPlan: null,
      }));

      try {
        // 1. 调用 API 发送消息（返回 202 + taskId）
        const response = await sessionApi.sendMessage(agentId, sessionId, {
          content: content.trim(),
          ...options,
        });

        const { user_message, task_id } = response;

        // 2. 追加用户消息到列表
        onAppendMessage?.(user_message);

        // 3. 创建流式占位 assistant 消息
        const placeholderMsg: SessionMessage = {
          id: `streaming-${task_id}`,
          session_id: sessionId,
          task_id,
          role: 'assistant',
          content: '',
          tool_calls: [],
          tool_results: [],
          status: 'streaming',
          error: null,
          cost: {},
          created_at: new Date().toISOString(),
        };
        onAppendMessage?.(placeholderMsg);

        setState((prev) => ({
          ...prev,
          isSending: false,
          isStreaming: true,
          currentTaskId: task_id,
        }));

        // 4. 连接 SSE 订阅任务事件
        disconnectStream();
        const stream = new AgentEventStream(window.location.origin, task_id);
        streamRef.current = stream;

        // —— LLM 流式增量输出 ——
        // 后端字段为 `text`（见 backend/src/infrastructure/agent/nodes/llm_call_node.py）
        stream.on('llm:chunk', (data) => {
          const chunk = data.text || '';
          if (!chunk) return;
          setState((prev) => ({
            ...prev,
            streamingContent: prev.streamingContent + chunk,
          }));
          onUpdateLastAssistant?.((msg) => ({
            ...msg,
            content: msg.content + chunk,
          }));
        });

        // —— 阶段变化 —— 后端字段为 `phase`（非 new_phase）
        stream.on('phase:changed', (data) => {
          setState((prev) => ({
            ...prev,
            currentPhase: (data.phase as AgentPhase) || prev.currentPhase,
          }));
        });

        // —— 工具调用 —— 后端字段为 `toolName` / `toolCallId`
        stream.on('tool:call', (data) => {
          if (PLAN_TOOL_NAMES.has(data.toolName || '')) {
            setState((prev) => ({
              ...prev,
              currentPlan: buildPlanFromToolInput(
                data.toolName || '',
                data.input || {},
                prev.currentPlan,
              ),
            }));
          }

          onUpdateLastAssistant?.((msg) => ({
            ...msg,
            tool_calls: [
              ...msg.tool_calls,
              {
                name: data.toolName || '',
                id: data.toolCallId || '',
                input: data.input || {},
              },
            ],
          }));
        });

        // —— 工具结果 —— 追加到 tool_results
        stream.on('tool:result', (data) => {
          if (PLAN_TOOL_NAMES.has(data.toolName || '')) {
            setState((prev) => ({
              ...prev,
              currentPlan: prev.currentPlan
                ? {
                    ...prev.currentPlan,
                    status: data.status === 'error' ? 'failed' : 'executing',
                  }
                : prev.currentPlan,
            }));
          }

          onUpdateLastAssistant?.((msg) => ({
            ...msg,
            tool_results: [
              ...msg.tool_results,
              {
                tool_name: data.toolName || '',
                id: data.toolCallId || '',
                status: data.status || 'success',
                result: data.output ?? data.error ?? '',
              },
            ],
          }));
        });

        stream.on('plan:created', (data) => {
          setState((prev) => ({
            ...prev,
            currentPlan: {
              ...ensurePlan(prev.currentPlan),
              goal: data.goal || prev.currentPlan?.goal || 'Plan',
              status: 'executing',
              executionOrder: data.execution_order || prev.currentPlan?.executionOrder,
            },
          }));
        });

        stream.on('plan:step_started', (data) => {
          setState((prev) => ({
            ...prev,
            currentPlan: {
              ...updatePlanStep(
                prev.currentPlan,
                data.step_id,
                (step) => ({ ...step, status: 'running' }),
                data.description,
              ),
              status: 'executing',
            },
          }));
        });

        stream.on('plan:step_completed', (data) => {
          const status: PlanStepStatus =
            data.status === 'failed' ? 'failed' : 'completed';
          setState((prev) => ({
            ...prev,
            currentPlan: updatePlanStep(
              {
                ...ensurePlan(prev.currentPlan),
                status: status === 'failed' ? 'failed' : 'executing',
              },
              data.step_id,
              (step) => ({
                ...step,
                status,
                result: data.result || null,
                error: data.error || null,
              }),
            ),
          }));
        });

        stream.on('plan:parallel_group_started', (data) => {
          setState((prev) => {
            const basePlan = ensurePlan(prev.currentPlan);
            return {
              ...prev,
              currentPlan: {
                ...basePlan,
                status: 'executing',
                steps: basePlan.steps.map((step) =>
                  data.step_ids.includes(step.id)
                    ? { ...step, status: 'running' }
                    : step,
                ),
              },
            };
          });
        });

        stream.on('plan:completed', (data) => {
          setState((prev) => {
            const basePlan = ensurePlan(prev.currentPlan);
            const stepResults = data.step_results || {};
            const steps = basePlan.steps.map((step) => {
              const result = stepResults[String(step.id)];
              if (!result) return step;
              return {
                ...step,
                status: result.status === 'failed' ? 'failed' : 'completed',
                result: result.result || step.result || null,
                error: result.error || step.error || null,
              } satisfies PlanStepProgress;
            });

            return {
              ...prev,
              currentPlan: {
                ...basePlan,
                status: steps.some((step) => step.status === 'failed')
                  ? 'failed'
                  : 'completed',
                steps,
              },
            };
          });
        });

        // —— 最终落库消息：替换占位 ——
        stream.on('session:message:saved', (data) => {
          const savedMsg = data.message;
          if (savedMsg) {
            onMessageSaved?.(savedMsg);
            onUpdateLastAssistant?.(() => savedMsg);
          }
        });

        // —— 任务完成 ——
        stream.on('task:completed', () => {
          setState((prev) => ({
            ...prev,
            isStreaming: false,
            currentPhase: 'complete',
            currentTaskId: null,
          }));
          disconnectStream();
        });

        // —— 任务取消 ——
        stream.on('task:cancelled', () => {
          const errorMsg = '任务已取消';
          setState((prev) => ({
            ...prev,
            isStreaming: false,
            currentPhase: 'cancelled',
            currentTaskId: null,
          }));
          onUpdateLastAssistant?.((msg) => ({
            ...msg,
            status: 'error',
            error: errorMsg,
          }));
          disconnectStream();
        });

        // —— 任务失败 ——
        stream.on('task:failed', (data) => {
          const errorMsg = data.error || '任务执行失败';
          setState((prev) => ({
            ...prev,
            isStreaming: false,
            currentPhase: 'failed',
            error: errorMsg,
            currentTaskId: null,
          }));
          onUpdateLastAssistant?.((msg) => ({
            ...msg,
            status: 'error',
            error: errorMsg,
          }));
          disconnectStream();
        });

        stream.connect();
      } catch (err: unknown) {
        const errorMessage =
          (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
          '发送消息失败';
        setState((prev) => ({
          ...prev,
          isSending: false,
          isStreaming: false,
          error: errorMessage,
        }));
      }
    },
    [agentId, sessionId, onAppendMessage, onUpdateLastAssistant, onMessageSaved, disconnectStream],
  );

  /**
   * 取消当前执行中的任务
   */
  const cancelExecution = useCallback(async () => {
    if (!state.currentTaskId) return;
    try {
      await taskApi.cancelTask(state.currentTaskId);
    } catch (err: unknown) {
      console.error('Cancel failed:', err);
    }
  }, [state.currentTaskId]);

  // 组件卸载时断开连接
  useEffect(() => {
    return () => {
      disconnectStream();
    };
  }, [disconnectStream]);

  useEffect(() => {
    setState(INITIAL_STATE);
    disconnectStream();
  }, [sessionId, disconnectStream]);

  return {
    ...state,
    sendMessage,
    cancelExecution,
  };
};
