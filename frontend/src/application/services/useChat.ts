/**
 * 应用层 - Chat 聊天 Hook
 *
 * 编排发送消息 → SSE 订阅 → 实时更新消息列表的完整流程。
 */
import { useState, useCallback, useRef, useEffect } from 'react';
import { sessionApi } from '@infrastructure/api/sessionApi';
import { taskApi } from '@infrastructure/api/taskApi';
import { AgentEventStream } from '@infrastructure/api/eventStream';
import type { SessionMessage, SendMessageRequest, MessageSegment } from '@domain/entities/session';
import type { AgentPhase } from '@domain/entities/task';

export type TaskStepStatus = 'pending' | 'running' | 'completed' | 'failed';
export type TaskStatus = 'planning' | 'executing' | 'completed' | 'failed';

export interface TaskStepProgress {
  id: number;
  description: string;
  status: TaskStepStatus;
  result?: string | null;
  error?: string | null;
}

export interface TaskProgress {
  goal: string;
  steps: TaskStepProgress[];
  status: TaskStatus;
  executionOrder?: unknown[];
}

export interface ChatState {
  isSending: boolean;
  isStreaming: boolean;
  isReplaying: boolean;
  streamingContent: string;
  currentPhase: AgentPhase;
  currentTaskId: string | null;
  error: string | null;
  currentTask: TaskProgress | null;
}

interface UseChatOptions {
  agentId: string;
  sessionId: string | null;
  onMessageSaved?: (msg: SessionMessage) => void;
  onAppendMessage?: (msg: SessionMessage) => void;
  onUpsertMessage?: (msg: SessionMessage) => void;
  onUpdateMessageById?: (
    messageId: string,
    updater: (msg: SessionMessage) => SessionMessage,
  ) => void;
  onUpdateLastAssistant?: (updater: (msg: SessionMessage) => SessionMessage) => void;
  onSessionUpdated?: () => void; // 新增：会话更新回调
}

const INITIAL_STATE: ChatState = {
  isSending: false,
  isStreaming: false,
  isReplaying: false,
  streamingContent: '',
  currentPhase: 'idle',
  currentTaskId: null,
  error: null,
  currentTask: null,
};

const TASK_TOOL_NAMES = new Set(['task_create', 'task_update']);

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const toStringValue = (value: unknown): string =>
  typeof value === 'string' ? value : value == null ? '' : String(value);

const toNumberValue = (value: unknown, fallback: number): number => {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
};

const normalizeTaskSteps = (rawSteps: unknown): TaskStepProgress[] => {
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

const buildTaskFromToolInput = (
  toolName: string,
  input: Record<string, unknown>,
  previousTask: TaskProgress | null,
): TaskProgress | null => {
  if (!TASK_TOOL_NAMES.has(toolName)) return null;

  // task_create: 创建新任务，替换现有任务
  if (toolName === 'task_create') {
    // 优先从 metadata 中读取 tasks，如果没有则从 input 中读取
    const metadata = input.metadata as Record<string, unknown> | undefined;
    const tasks = input.tasks || metadata?.tasks || input.steps;
    const incomingSteps = normalizeTaskSteps(tasks);
    const goal = toStringValue(input.goal) || toStringValue(metadata?.goal) || 'Task';
    
    return {
      goal,
      steps: incomingSteps,
      status: 'planning',
      executionOrder: Array.isArray(input.execution_order)
        ? input.execution_order
        : undefined,
    };
  }

  // task_update: 更新现有任务的状态
  if (toolName === 'task_update' && previousTask) {
    const taskId = input.task_id;
    const status = toStringValue(input.status);
    const result = toStringValue(input.result);

    if (!previousTask.steps.length) return previousTask;

    const updatedSteps = previousTask.steps.map((step) => {
      if (step.id !== taskId) return step;
      return {
        ...step,
        status: (status === 'completed' ? 'completed' : status === 'failed' ? 'failed' : step.status) as TaskStepStatus,
        result: result || step.result,
      };
    });

    // 检查是否所有任务都完成了
    const allCompleted = updatedSteps.every(
      (s) => s.status === 'completed' || s.status === 'failed'
    );
    const hasFailed = updatedSteps.some((s) => s.status === 'failed');

    return {
      ...previousTask,
      steps: updatedSteps,
      status: allCompleted ? (hasFailed ? 'failed' : 'completed') : 'executing',
    };
  }

  return previousTask;
};

const ensureTask = (task: TaskProgress | null): TaskProgress => ({
  goal: task?.goal || 'Task',
  steps: task?.steps || [],
  status: task?.status || 'planning',
  executionOrder: task?.executionOrder,
});

const updateTaskStep = (
  task: TaskProgress | null,
  stepId: number,
  updater: (step: TaskStepProgress) => TaskStepProgress,
  description?: string,
): TaskProgress => {
  const currentTask = ensureTask(task);
  const stepIndex = currentTask.steps.findIndex((step) => step.id === stepId);

  if (stepIndex === -1) {
    return {
      ...currentTask,
      steps: [
        ...currentTask.steps,
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
    ...currentTask,
    steps: currentTask.steps.map((step) =>
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
  onUpsertMessage,
  onUpdateMessageById,
  onUpdateLastAssistant,
  onSessionUpdated,
}: UseChatOptions) => {
  const [state, setState] = useState<ChatState>(INITIAL_STATE);

  const streamRef = useRef<AgentEventStream | null>(null);
  const subStreamsRef = useRef<Map<string, AgentEventStream>>(new Map());
  const subAgentMessagesRef = useRef<Set<string>>(new Set());
  const mainMessageIdRef = useRef<string | null>(null);

  // —— localStorage 持久化辅助函数 (跨标签页存活, 支持心跳续期) ——
  const TASK_STATE_KEY = 'activeTaskState';
  const HEARTBEAT_INTERVAL_MS = 30_000; // 30s 心跳

  const heartbeatTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // 用 ref 保持最新的 sessionId/agentId，避免 useCallback 依赖链导致无限重渲染
  const latestSessionIdRef = useRef(sessionId);
  const latestAgentIdRef = useRef(agentId);
  latestSessionIdRef.current = sessionId;
  latestAgentIdRef.current = agentId;

  const stopHeartbeat = useCallback(() => {
    if (heartbeatTimerRef.current !== null) {
      clearInterval(heartbeatTimerRef.current);
      heartbeatTimerRef.current = null;
    }
  }, []);

  const startHeartbeat = useCallback(() => {
    stopHeartbeat();
    heartbeatTimerRef.current = setInterval(() => {
      try {
        const raw = localStorage.getItem(TASK_STATE_KEY);
        if (!raw) return;
        const state = JSON.parse(raw);
        state.timestamp = Date.now();
        localStorage.setItem(TASK_STATE_KEY, JSON.stringify(state));
      } catch {
        // 心跳失败静默忽略
      }
    }, HEARTBEAT_INTERVAL_MS);
  }, [stopHeartbeat]);

  const saveTaskState = useCallback((taskId: string, sid?: string) => {
    try {
      const state = JSON.stringify({
        taskId,
        sessionId: sid || latestSessionIdRef.current || '',
        agentId: latestAgentIdRef.current,
        timestamp: Date.now(),
      });
      localStorage.setItem(TASK_STATE_KEY, state);
      startHeartbeat();
    } catch (err) {
      console.warn('[useChat] Failed to save task state to localStorage:', err);
    }
  }, [startHeartbeat]);

  const clearTaskState = useCallback(() => {
    try {
      localStorage.removeItem(TASK_STATE_KEY);
      stopHeartbeat();
    } catch (err) {
      console.warn('[useChat] Failed to clear task state from localStorage:', err);
    }
  }, [stopHeartbeat]);

  // 切换会话时重置 UI 状态（不清理 localStorage：页面刷新恢复时仍需读取，由任务终态事件清理）
  useEffect(() => {
    setState((prev) => ({ ...prev, currentTask: null }));
    disconnectAllStreams();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  const updateMessage = useCallback((
    messageId: string | null,
    updater: (msg: SessionMessage) => SessionMessage,
  ) => {
    if (messageId && onUpdateMessageById) {
      onUpdateMessageById(messageId, updater);
      return;
    }
    onUpdateLastAssistant?.(updater);
  }, [onUpdateLastAssistant, onUpdateMessageById]);

  const disconnectSubStreams = useCallback(() => {
    subStreamsRef.current.forEach((stream) => stream.disconnect());
    subStreamsRef.current.clear();
    subAgentMessagesRef.current.clear();
  }, []);

  const disconnectStream = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.disconnect();
      streamRef.current = null;
    }
  }, []);

  const disconnectAllStreams = useCallback(() => {
    disconnectStream();
    disconnectSubStreams();
  }, [disconnectStream, disconnectSubStreams]);

  /**
   * 向消息的 segments 追加内容，同类型连续追加（不创建新片段）
   * 返回更新后的 segments 和是否创建了新片段
   */
  const appendSegmentContent = useCallback((
    msg: SessionMessage,
    type: MessageSegment['type'],
    content: string,
  ): { segments: MessageSegment[]; created: boolean } => {
    const segments = [...(msg.segments || [])];
    const lastSeg = segments[segments.length - 1];

    if (lastSeg && lastSeg.type === type) {
      segments[segments.length - 1] = {
        ...lastSeg,
        content: (lastSeg.content || '') + content,
      };
      return { segments, created: false };
    }
    segments.push({ type, content });
    return { segments, created: true };
  }, []);

  const bindMessageStream = useCallback((
    stream: AgentEventStream,
    messageId: string,
    onChunk?: (chunk: string) => void,
  ) => {
    // 处理思考内容流式输出
    stream.on('thinking:chunk', (data) => {
      const chunk = data.text || '';
      if (!chunk) return;
      const targetMessageId = data.sub_task_id || messageId;
      updateMessage(targetMessageId, (msg) => {
        const { segments } = appendSegmentContent(msg, 'thinking', chunk);
        return {
          ...msg,
          thinking_content: (msg.thinking_content || '') + chunk,
          has_thinking: true,
          segments,
        };
      });
    });

    stream.on('llm:chunk', (data) => {
      const chunk = data.text || '';
      if (!chunk) return;
      const targetMessageId = data.sub_task_id || messageId;
      if (!data.sub_task_id) {
        onChunk?.(chunk);
      }
      updateMessage(targetMessageId, (msg) => {
        const { segments } = appendSegmentContent(msg, 'text', chunk);
        return { ...msg, content: msg.content + chunk, segments };
      });
    });

    stream.on('tool:call', (data) => {
      const targetMessageId = data.sub_task_id || messageId;
      updateMessage(targetMessageId, (msg) => {
        const segments = [...(msg.segments || [])];
        segments.push({
          type: 'tool',
          content: data.toolName || '',
          toolInput: data.input || {},
          toolCallId: data.toolCallId || '',
          toolStatus: 'running',
        });
        return {
          ...msg,
          segments,
          tool_calls: [
            ...msg.tool_calls,
            { name: data.toolName || '', id: data.toolCallId || '', input: data.input || {} },
          ],
        };
      });
    });

    stream.on('tool:result', (data) => {
      const targetMessageId = data.sub_task_id || messageId;
      updateMessage(targetMessageId, (msg) => {
        const segments = [...(msg.segments || [])];
        // 反向查找最后一个匹配的 tool 片段并更新其结果
        for (let i = segments.length - 1; i >= 0; i--) {
          const seg = segments[i];
          if (
            seg.type === 'tool' &&
            seg.toolStatus === 'running' &&
            (!data.toolCallId || seg.toolCallId === data.toolCallId)
          ) {
            segments[i] = {
              ...seg,
              toolResult: (data.output ?? data.error ?? '') as string,
              toolStatus: data.status || 'success',
            };
            break;
          }
        }
        return {
          ...msg,
          segments,
          tool_results: [
            ...msg.tool_results,
            {
              tool_name: data.toolName || '',
              id: data.toolCallId || '',
              status: data.status || 'success',
              result: data.output ?? data.error ?? '',
            },
          ],
        };
      });
    });

    // 危险命令待确认：更新对应 tool 片段为 awaiting_confirmation 并填入风险原因
    stream.on('tool:confirmation_required', (data) => {
      const targetMessageId = data.sub_task_id || messageId;
      updateMessage(targetMessageId, (msg) => {
        const segments = [...(msg.segments || [])];
        // 反向查找最后一个匹配的 tool 片段并更新其状态
        for (let i = segments.length - 1; i >= 0; i--) {
          const seg = segments[i];
          if (
            seg.type === 'tool' &&
            (!data.toolCallId || seg.toolCallId === data.toolCallId)
          ) {
            segments[i] = {
              ...seg,
              toolStatus: 'awaiting_confirmation',
              riskReason: data.riskReason || seg.riskReason,
            };
            break;
          }
        }
        return { ...msg, segments };
      });
    });

    // 处理 LLM 完成事件，保存完整思考内容
    stream.on('llm:complete', (data) => {
      const targetMessageId = data.sub_task_id || messageId;
      updateMessage(targetMessageId, (msg) => ({
        ...msg,
        thinking_content: data.thinkingText || msg.thinking_content,
        has_thinking: data.hasThinking || !!data.thinkingText,
      }));
    });
  }, [updateMessage, appendSegmentContent]);

  const connectSubAgentStream = useCallback((
    subTaskId: string,
    stepId?: number,
    description?: string,
  ) => {
    if (!sessionId || subAgentMessagesRef.current.has(subTaskId)) return;

    const message: SessionMessage = {
      id: subTaskId,
      session_id: sessionId,
      task_id: subTaskId,
      role: 'assistant',
      content: '',
      tool_calls: [],
      tool_results: [],
      status: 'streaming',
      error: null,
      cost: {},
      created_at: new Date().toISOString(),
      meta: {
        isSubAgent: true,
        stepId,
        title: description,
      },
    };
    onUpsertMessage?.(message);
    subAgentMessagesRef.current.add(subTaskId);
  }, [onUpsertMessage, sessionId]);

  const finalizeSubAgentMessage = useCallback((
    subTaskId: string,
    status: 'completed' | 'error',
    result?: string | null,
    error?: string | null,
  ) => {
    updateMessage(subTaskId, (msg) => ({
      ...msg,
      content: msg.content || result || error || '',
      status,
      error: error || null,
    }));
    const subStream = subStreamsRef.current.get(subTaskId);
    if (subStream) {
      subStream.disconnect();
      subStreamsRef.current.delete(subTaskId);
    }
    subAgentMessagesRef.current.delete(subTaskId);
  }, [updateMessage]);

  // —— 页面刷新后恢复活动任务流 / 手动重放 ——
  //
  // 恢复策略 (优先级从高到低):
  //   1. API 查询: GET /api/agents/{agentId}/sessions/{sessionId}/active-tasks
  //   2. localStorage 快路径: 读取 'activeTaskState' (含心跳续期)
  //   3. forceReplay: 调用方显式传入 taskId
  //
  // localStorage 不再有硬超时 — 心跳每 30s 更新 timestamp，
  // 仅当后端 active-tasks API 不可用时作为 fallback。
  const restoreActiveStream = useCallback(async (forceReplay = false, taskId?: string) => {
    console.log('[useChat] restoreActiveStream called:', {
      forceReplay,
      taskId,
      agentId,
      sessionId,
    });

    // —— 确定恢复目标 taskId ——
    let targetTaskId: string | null = null;
    let targetSessionId: string | null = null;

    // 优先级 1: forceReplay 时使用显式传入的 taskId
    if (forceReplay && taskId) {
      targetTaskId = taskId;
      targetSessionId = sessionId;
    }

    // 优先级 2: 查询后端 active-tasks API
    let apiFailed = false;
    if (!targetTaskId && agentId && sessionId) {
      try {
        const activeTasksResp = await sessionApi.getActiveTasks(agentId, sessionId);
        const activeTasks = activeTasksResp.tasks || [];
        if (activeTasks.length > 0) {
          // 取最新的活跃任务
          const latest = activeTasks[0];
          targetTaskId = latest.task_id;
          targetSessionId = sessionId;
          console.log('[useChat] Found active task via API:', latest.task_id, latest.status);
        }
      } catch (err) {
        apiFailed = true;
        console.warn('[useChat] Failed to query active-tasks API, falling back to localStorage:', err);
      }
    }

    // 优先级 3: localStorage fallback (仅当 API 不可用；校验 agentId + sessionId 防止跨会话恢复)
    if (apiFailed && !targetTaskId) {
      try {
        const raw = localStorage.getItem('activeTaskState');
        if (raw) {
          const state = JSON.parse(raw);
          // 校验 agentId + sessionId 匹配
          if (state.agentId === agentId && state.sessionId === sessionId && state.taskId) {
            targetTaskId = state.taskId;
            targetSessionId = state.sessionId;
            console.log('[useChat] Found active task via localStorage:', targetTaskId);
          }
        }
      } catch {
        // localStorage 解析失败, 忽略
      }
    }

    if (!targetTaskId || !targetSessionId) {
      console.log('[useChat] No active task to restore');
      return;
    }

    // 如果已有连接且不是强制重放，不重复恢复
    if (streamRef.current && !forceReplay) {
      console.log('[useChat] Stream already connected, skipping restore');
      return;
    }

    console.log('[useChat] Restoring/replaying stream for task:', targetTaskId);

    // 断开之前的连接
    if (streamRef.current) {
      streamRef.current.disconnect();
      streamRef.current = null;
    }

    // 设置状态为流式中
    setState((prev) => ({
      ...prev,
      isStreaming: true,
      isReplaying: true,
      currentTaskId: targetTaskId,
      currentPhase: 'thinking',
    }));

    // 创建占位消息
    const placeholderMsg: SessionMessage = {
      id: `streaming-${targetTaskId}`,
      session_id: targetSessionId,
      task_id: targetTaskId,
      role: 'assistant',
      content: '',
      tool_calls: [],
      tool_results: [],
      thinking_content: '',
      has_thinking: false,
      status: 'streaming',
      error: null,
      cost: {},
      created_at: new Date().toISOString(),
    };

    if (forceReplay) {
      // 手动重放：将最后一条 assistant 消息替换为占位消息
      onUpdateLastAssistant?.((msg) => ({
        ...placeholderMsg,
        session_id: msg.session_id,
      }));
    } else {
      // 页面恢复：追加新消息
      onAppendMessage?.(placeholderMsg);
    }

    // 保存到 localStorage (用于跨标签页恢复), 启动心跳
    saveTaskState(targetTaskId);

    // 连接 SSE(后端会自动回放所有事件)
    const stream = new AgentEventStream(window.location.origin, targetTaskId);
    if (forceReplay) {
      stream.enableReplayMode();
    }
    streamRef.current = stream;
    mainMessageIdRef.current = placeholderMsg.id;

    // 绑定所有事件监听器
    bindStreamEvents(stream, placeholderMsg.id, forceReplay);

    stream.connect();
  }, [
    agentId,
    sessionId,
    onAppendMessage,
    onMessageSaved,
    onUpdateLastAssistant,
    bindMessageStream,
    connectSubAgentStream,
    disconnectAllStreams,
    finalizeSubAgentMessage,
    updateMessage,
    saveTaskState,
  ]);

  /**
   * 绑定 SSE 事件监听器到 stream（共享于 restoreActiveStream 与 sendMessage）
   */
  const bindStreamEvents = useCallback((
    stream: AgentEventStream,
    placeholderMsgId: string,
    isReplay: boolean,
  ) => {
    bindMessageStream(stream, placeholderMsgId, (chunk) => {
      setState((prev) => ({
        ...prev,
        streamingContent: prev.streamingContent + chunk,
      }));
    });

    // —— 阶段变化 ——
    stream.on('phase:changed', (data) => {
      if (data.sub_task_id) return;
      setState((prev) => ({
        ...prev,
        currentPhase: (data.phase as AgentPhase) || prev.currentPhase,
      }));
    });

    // —— 工具调用 ——
    stream.on('tool:call', (data) => {
      if (TASK_TOOL_NAMES.has(data.toolName || '')) {
        setState((prev) => ({
          ...prev,
          currentTask: buildTaskFromToolInput(
            data.toolName || '',
            data.input || {},
            prev.currentTask,
          ),
        }));
      }
    });

    // —— 工具结果 ——
    stream.on('tool:result', (data) => {
      if (TASK_TOOL_NAMES.has(data.toolName || '')) {
        if (data.toolName === 'task_update' && data.metadata) {
          const metadata = data.metadata as Record<string, unknown>;
          if (metadata.type === 'task_update') {
            setState((prev) => ({
              ...prev,
              currentTask: buildTaskFromToolInput(
                'task_update',
                {
                  task_id: metadata.task_id,
                  status: metadata.status,
                  result: metadata.result,
                },
                prev.currentTask,
              ),
            }));
          }
        } else {
          setState((prev) => ({
            ...prev,
            currentTask: prev.currentTask
              ? {
                  ...prev.currentTask,
                  status: data.status === 'error' ? 'failed' : 'executing',
                }
              : prev.currentTask,
          }));
        }
      }
    });

    stream.on('step:created', (data) => {
      setState((prev) => ({
        ...prev,
        currentTask: {
          ...ensureTask(prev.currentTask),
          goal: data.goal || prev.currentTask?.goal || 'Task',
          status: 'executing',
          executionOrder: data.execution_order || prev.currentTask?.executionOrder,
        },
      }));
    });

    stream.on('step:started', (data) => {
      setState((prev) => ({
        ...prev,
        currentTask: {
          ...updateTaskStep(
            prev.currentTask,
            data.step_id,
            (step) => ({ ...step, status: 'running' }),
            data.description,
          ),
          status: 'executing',
        },
      }));
    });

    stream.on('step:completed', (data) => {
      const status: TaskStepStatus =
        data.status === 'failed' ? 'failed' : 'completed';
      setState((prev) => ({
        ...prev,
        currentTask: updateTaskStep(
          {
            ...ensureTask(prev.currentTask),
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

    stream.on('step:parallel_group_started', (data) => {
      setState((prev) => {
        const baseTask = ensureTask(prev.currentTask);
        return {
          ...prev,
          currentTask: {
            ...baseTask,
            status: 'executing',
            steps: baseTask.steps.map((step) =>
              data.step_ids.includes(step.id)
                ? { ...step, status: 'running' }
                : step,
            ),
          },
        };
      });
    });

    stream.on('step:all_completed', (data) => {
      setState((prev) => {
        const baseTask = ensureTask(prev.currentTask);
        const stepResults = data.step_results || {};
        const steps = baseTask.steps.map((step) => {
          const result = stepResults[String(step.id)];
          if (!result) return step;
          return {
            ...step,
            status: result.status === 'failed' ? 'failed' : 'completed',
            result: result.result || step.result || null,
            error: result.error || step.error || null,
          } satisfies TaskStepProgress;
        });

        return {
          ...prev,
          currentTask: {
            ...baseTask,
            status: steps.some((step) => step.status === 'failed')
              ? 'failed'
              : 'completed',
            steps,
          },
        };
      });
    });

    // —— 最终落库消息:替换占位 ——
    // 保护：如果流式构建的内容比落库内容更丰富（更长），保留流式版本
    stream.on('session:message:saved', (data) => {
      const savedMsg = data.message;
      if (savedMsg) {
        onMessageSaved?.(savedMsg);
        updateMessage(mainMessageIdRef.current, (prevMsg) => {
          const streamContent = prevMsg.content || '';
          const savedContent = savedMsg.content || '';
          // 优先保留更长的内容（流式构建的通常更完整）
          const finalContent = streamContent.length >= savedContent.length
            ? streamContent
            : savedContent;
          return {
            ...savedMsg,
            content: finalContent,
            thinking_content: prevMsg.thinking_content || savedMsg.thinking_content || '',
            has_thinking: prevMsg.has_thinking || savedMsg.has_thinking || false,
            segments: prevMsg.segments || savedMsg.segments,
          };
        });
        mainMessageIdRef.current = savedMsg.id;
      }
    });

    stream.on('sub_agent:started', (data) => {
      if (!data.sub_task_id) return;
      connectSubAgentStream(
        data.sub_task_id,
        data.step_id,
        data.description,
      );
    });

    stream.on('sub_agent:completed', (data) => {
      if (!data.sub_task_id) return;
      finalizeSubAgentMessage(
        data.sub_task_id,
        'completed',
        data.result,
        data.error,
      );
    });

    stream.on('sub_agent:failed', (data) => {
      if (!data.sub_task_id) return;
      finalizeSubAgentMessage(
        data.sub_task_id,
        'error',
        data.result,
        data.error,
      );
    });

    // —— 任务完成 ——
    stream.on('task:completed', (data) => {
      if (data.sub_task_id) {
        finalizeSubAgentMessage(data.sub_task_id, 'completed', data.result, null);
        return;
      }
      setState((prev) => ({
        ...prev,
        isStreaming: false,
        isReplaying: false,
        currentPhase: 'complete',
        currentTaskId: null,
        streamingContent: '',
      }));
      mainMessageIdRef.current = null;
      disconnectAllStreams();
      if (!isReplay) {
        clearTaskState();
      }
    });

    // —— 任务取消 ——
    stream.on('task:cancelled', (data) => {
      if (data.sub_task_id) {
        finalizeSubAgentMessage(data.sub_task_id, 'error', null, '任务已取消');
        return;
      }
      const errorMsg = '任务已取消';
      setState((prev) => ({
        ...prev,
        isStreaming: false,
        isReplaying: false,
        currentPhase: 'cancelled',
        currentTaskId: null,
      }));
      updateMessage(mainMessageIdRef.current, (msg) => ({
        ...msg,
        status: 'error',
        error: errorMsg,
      }));
      mainMessageIdRef.current = null;
      disconnectAllStreams();
      if (!isReplay) {
        clearTaskState();
      }
    });

    // —— 任务失败 ——
    stream.on('task:failed', (data) => {
      if (data.sub_task_id) {
        finalizeSubAgentMessage(data.sub_task_id, 'error', null, data.error);
        return;
      }
      const errorMsg = data.error || '任务执行失败';
      setState((prev) => ({
        ...prev,
        isStreaming: false,
        isReplaying: false,
        currentPhase: 'failed',
        error: errorMsg,
        currentTaskId: null,
      }));
      updateMessage(mainMessageIdRef.current, (msg) => ({
        ...msg,
        status: 'error',
        error: errorMsg,
      }));
      mainMessageIdRef.current = null;
      disconnectAllStreams();
      if (!isReplay) {
        clearTaskState();
      }
    });
  }, [
    bindMessageStream,
    connectSubAgentStream,
    disconnectAllStreams,
    finalizeSubAgentMessage,
    updateMessage,
    onMessageSaved,
    clearTaskState,
  ]);

  /**
   * 发送消息
   */
  const sendMessage = useCallback(
    async (content: string, options?: Partial<SendMessageRequest>, targetSessionId?: string) => {
      const sid = targetSessionId || sessionId;
      if (!sid || !agentId || !content.trim()) return;

      setState((prev) => ({
        ...prev,
        isSending: true,
        error: null,
        streamingContent: '',
        currentPhase: 'idle',
        currentTask: null,
      }));

      try {
        // 1. 调用 API 发送消息（返回 202 + taskId）
        const response = await sessionApi.sendMessage(agentId, sid, {
          content: content.trim(),
          ...options,
        });

        const { user_message, task_id } = response;

        // 2. 追加用户消息到列表
        onAppendMessage?.(user_message);

        // 3. 延迟刷新会话列表以获取 LLM 生成的标题
        // 后端异步生成标题，通常 1-3 秒完成
        setTimeout(() => {
          onSessionUpdated?.();
        }, 2000);

        // 3. 创建流式占位 assistant 消息
        const placeholderMsg: SessionMessage = {
          id: `streaming-${task_id}`,
          session_id: sid,
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

        // 保存任务状态到 localStorage (用于页面刷新后恢复, 含心跳续期)
        saveTaskState(task_id, sid);

        // 4. 连接 SSE 订阅任务事件
        disconnectAllStreams();
        const stream = new AgentEventStream(window.location.origin, task_id);
        streamRef.current = stream;
        mainMessageIdRef.current = placeholderMsg.id;

        // 绑定所有事件监听器 (共享于 restoreActiveStream)
        bindStreamEvents(stream, placeholderMsg.id, false);

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
    [
      agentId,
      sessionId,
      onAppendMessage,
      onMessageSaved,
      onSessionUpdated,
      bindStreamEvents,
      disconnectAllStreams,
      saveTaskState,
    ],
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

  // 组件卸载时断开连接 + 停止心跳
  useEffect(() => {
    return () => {
      disconnectAllStreams();
      stopHeartbeat();
    };
  }, [disconnectAllStreams]);

  useEffect(() => {
    setState(INITIAL_STATE);
    mainMessageIdRef.current = null;
    disconnectAllStreams();
  }, [sessionId, disconnectAllStreams]);

  // 页面加载时恢复活动任务流 (仅 sessionId/agentId 变化时触发)
  const restoreActiveStreamRef = useRef(restoreActiveStream);
  restoreActiveStreamRef.current = restoreActiveStream;

  useEffect(() => {
    restoreActiveStreamRef.current();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  return {
    ...state,
    sendMessage,
    cancelExecution,
    replayStream: restoreActiveStream,
  };
};
