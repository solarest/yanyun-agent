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

  // —— sessionStorage 持久化辅助函数 ——
  const saveTaskState = (taskId: string) => {
    try {
      sessionStorage.setItem('activeTaskId', taskId);
      sessionStorage.setItem('activeSessionId', sessionId || '');
      sessionStorage.setItem('taskStateTimestamp', Date.now().toString());
    } catch (err) {
      console.warn('[useChat] Failed to save task state to sessionStorage:', err);
    }
  };

  const clearTaskState = () => {
    try {
      sessionStorage.removeItem('activeTaskId');
      sessionStorage.removeItem('activeSessionId');
      sessionStorage.removeItem('taskStateTimestamp');
    } catch (err) {
      console.warn('[useChat] Failed to clear task state from sessionStorage:', err);
    }
  };

  // 切换会话时重置任务状态
  useEffect(() => {
    setState((prev) => ({ ...prev, currentTask: null }));
    clearTaskState(); // 清除之前的任务状态
    disconnectAllStreams(); // 断开之前的连接
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
      updateMessage(targetMessageId, (msg) => ({
        ...msg,
        thinking_content: (msg.thinking_content || '') + chunk,
        has_thinking: true,
      }));
    });

    stream.on('llm:chunk', (data) => {
      const chunk = data.text || '';
      if (!chunk) return;
      const targetMessageId = data.sub_task_id || messageId;
      if (!data.sub_task_id) {
        onChunk?.(chunk);
      }
      updateMessage(targetMessageId, (msg) => ({
        ...msg,
        content: msg.content + chunk,
      }));
    });

    stream.on('tool:call', (data) => {
      const targetMessageId = data.sub_task_id || messageId;
      updateMessage(targetMessageId, (msg) => ({
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

    stream.on('tool:result', (data) => {
      const targetMessageId = data.sub_task_id || messageId;
      updateMessage(targetMessageId, (msg) => ({
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

    // 处理 LLM 完成事件，保存完整思考内容
    stream.on('llm:complete', (data) => {
      const targetMessageId = data.sub_task_id || messageId;
      updateMessage(targetMessageId, (msg) => ({
        ...msg,
        thinking_content: data.thinkingText || msg.thinking_content,
        has_thinking: data.hasThinking || !!data.thinkingText,
      }));
    });
  }, [updateMessage]);

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
  const restoreActiveStream = useCallback((forceReplay = false, taskId?: string) => {
    console.log('[useChat] restoreActiveStream called:', {
      forceReplay,
      taskId,
      stateCurrentTaskId: state.currentTaskId,
      sessionId,
    });
    
    const savedTaskId = forceReplay 
      ? (taskId || state.currentTaskId) 
      : sessionStorage.getItem('activeTaskId');
    const savedSessionId = forceReplay ? sessionId : sessionStorage.getItem('activeSessionId');
    const timestamp = forceReplay ? Date.now().toString() : sessionStorage.getItem('taskStateTimestamp');

    console.log('[useChat] Restore/replay details:', {
      savedTaskId,
      savedSessionId,
      timestamp,
    });

    if (!savedTaskId || !savedSessionId) {
      console.warn('[useChat] No active task to replay', {
        savedTaskId,
        savedSessionId,
      });
      return;
    }

    // 非强制重放时，检查是否超过5分钟(避免恢复过期的任务)
    if (!forceReplay && Date.now() - parseInt(timestamp || '0') > 5 * 60 * 1000) {
      console.warn('[useChat] Task state expired');
      clearTaskState();
      return;
    }

    // 如果已有连接且不是强制重放，不重复恢复
    if (streamRef.current && !forceReplay) {
      console.log('[useChat] Stream already connected, skipping restore');
      return;
    }

    console.log('[useChat] Restoring/replaying stream for task:', savedTaskId);

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
      currentTaskId: savedTaskId,
      currentPhase: 'thinking',
    }));

    // 创建占位消息
    const placeholderMsg: SessionMessage = {
      id: `streaming-${savedTaskId}`,
      session_id: savedSessionId,
      task_id: savedTaskId,
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
      // 手动重放：将最后一条 assistant 消息替换为占位消息（包括 ID），
      // 确保后续 updateMessageById 能通过 placeholderMsg.id 找到目标
      onUpdateLastAssistant?.((msg) => ({
        ...placeholderMsg,
        session_id: msg.session_id, // 保留原始 session 信息
      }));
    } else {
      // 页面恢复：追加新消息
      onAppendMessage?.(placeholderMsg);
    }

    // 连接 SSE(后端会自动回放所有事件)
    const stream = new AgentEventStream(window.location.origin, savedTaskId);
    if (forceReplay) {
      stream.enableReplayMode();
    }
    streamRef.current = stream;
    mainMessageIdRef.current = placeholderMsg.id;

    // 绑定所有事件监听器(与sendMessage中相同)
    bindMessageStream(stream, placeholderMsg.id, (chunk) => {
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
    stream.on('session:message:saved', (data) => {
      const savedMsg = data.message;
      if (savedMsg) {
        onMessageSaved?.(savedMsg);
        updateMessage(mainMessageIdRef.current, () => savedMsg);
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
      if (!forceReplay) {
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
      if (!forceReplay) {
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
      if (!forceReplay) {
        clearTaskState();
      }
    });

    stream.connect();
  }, [
    sessionId,
    state.currentTaskId,
    onAppendMessage,
    onMessageSaved,
    onUpdateLastAssistant,
    bindMessageStream,
    connectSubAgentStream,
    disconnectAllStreams,
    finalizeSubAgentMessage,
    updateMessage,
  ]);

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
        currentTask: null,
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

        // 3. 延迟刷新会话列表以获取 LLM 生成的标题
        // 后端异步生成标题，通常 1-3 秒完成
        setTimeout(() => {
          onSessionUpdated?.();
        }, 2000);

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

        // 保存任务状态到 sessionStorage(用于页面刷新后恢复)
        saveTaskState(task_id);

        // 4. 连接 SSE 订阅任务事件
        disconnectAllStreams();
        const stream = new AgentEventStream(window.location.origin, task_id);
        streamRef.current = stream;
        mainMessageIdRef.current = placeholderMsg.id;

        bindMessageStream(stream, placeholderMsg.id, (chunk) => {
          setState((prev) => ({
            ...prev,
            streamingContent: prev.streamingContent + chunk,
          }));
        });

        // —— 阶段变化 —— 后端字段为 `phase`（非 new_phase）
        stream.on('phase:changed', (data) => {
          if (data.sub_task_id) return;
          setState((prev) => ({
            ...prev,
            currentPhase: (data.phase as AgentPhase) || prev.currentPhase,
          }));
        });

        // —— 工具调用 —— 后端字段为 `toolName` / `toolCallId`
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

        // —— 工具结果 —— 追加到 tool_results
        stream.on('tool:result', (data) => {
          if (TASK_TOOL_NAMES.has(data.toolName || '')) {
            // 对于 task_update，从 metadata 中提取更新信息
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
              // task_create 或其他工具
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

        // —— 最终落库消息：替换占位 ——
        stream.on('session:message:saved', (data) => {
          const savedMsg = data.message;
          if (savedMsg) {
            onMessageSaved?.(savedMsg);
            updateMessage(mainMessageIdRef.current, () => savedMsg);
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
            currentPhase: 'complete',
            currentTaskId: null,
          }));
          mainMessageIdRef.current = null;
          disconnectAllStreams();
          clearTaskState();
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
          clearTaskState();
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
          clearTaskState();
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
    [
      agentId,
      sessionId,
      onAppendMessage,
      onMessageSaved,
      bindMessageStream,
      connectSubAgentStream,
      disconnectAllStreams,
      finalizeSubAgentMessage,
      updateMessage,
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

  // 组件卸载时断开连接
  useEffect(() => {
    return () => {
      disconnectAllStreams();
    };
  }, [disconnectAllStreams]);

  useEffect(() => {
    setState(INITIAL_STATE);
    mainMessageIdRef.current = null;
    disconnectAllStreams();
  }, [sessionId, disconnectAllStreams]);

  // 页面加载时恢复活动任务流
  useEffect(() => {
    restoreActiveStream();
  }, [restoreActiveStream]);

  return {
    ...state,
    sendMessage,
    cancelExecution,
    replayStream: restoreActiveStream,
  };
};
