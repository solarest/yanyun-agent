/**
 * 应用层 - Chat 聊天 Hook
 *
 * 编排发送消息 → SSE 订阅 → 实时更新消息列表的完整流程。
 */
import { useState, useCallback, useRef, useEffect } from 'react';
import { sessionApi } from '../../infrastructure/api/sessionApi';
import { taskApi } from '../../infrastructure/api/taskApi';
import { AgentEventStream } from '../../infrastructure/api/eventStream';
import type { SessionMessage, SendMessageRequest } from '../../domain/entities/session';
import type { AgentPhase } from '../../domain/entities/task';

export interface ChatState {
  isSending: boolean;
  isStreaming: boolean;
  streamingContent: string;
  currentPhase: AgentPhase;
  currentTaskId: string | null;
  error: string | null;
}

interface UseChatOptions {
  agentId: string;
  sessionId: string | null;
  onMessageSaved?: (msg: SessionMessage) => void;
  onAppendMessage?: (msg: SessionMessage) => void;
  onUpdateLastAssistant?: (updater: (msg: SessionMessage) => SessionMessage) => void;
}

export const useChat = ({
  agentId,
  sessionId,
  onMessageSaved,
  onAppendMessage,
  onUpdateLastAssistant,
}: UseChatOptions) => {
  const [state, setState] = useState<ChatState>({
    isSending: false,
    isStreaming: false,
    streamingContent: '',
    currentPhase: 'idle',
    currentTaskId: null,
    error: null,
  });

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
  const sendMessage = useCallback(async (content: string, options?: Partial<SendMessageRequest>) => {
    if (!sessionId || !agentId || !content.trim()) return;

    setState(prev => ({
      ...prev,
      isSending: true,
      error: null,
      streamingContent: '',
      currentPhase: 'idle',
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

      setState(prev => ({
        ...prev,
        isSending: false,
        isStreaming: true,
        currentTaskId: task_id,
      }));

      // 4. 连接 SSE 订阅任务事件
      disconnectStream();
      // 使用空 baseUrl 时，EventSource 会使用相对路径（由 vite proxy 处理）
      const stream = new AgentEventStream(window.location.origin, task_id);
      streamRef.current = stream;

      // 监听 LLM 流式输出
      stream.on('llm:chunk', (data) => {
        const chunk = (data as { content?: string }).content || '';
        setState(prev => ({
          ...prev,
          streamingContent: prev.streamingContent + chunk,
        }));
        onUpdateLastAssistant?.(msg => ({
          ...msg,
          content: msg.content + chunk,
        }));
      });

      // 监听阶段变化
      stream.on('phase:changed', (data) => {
        setState(prev => ({
          ...prev,
          currentPhase: (data.new_phase as AgentPhase) || prev.currentPhase,
        }));
      });

      // 监听工具调用
      stream.on('tool:call', (data) => {
        onUpdateLastAssistant?.(msg => ({
          ...msg,
          tool_calls: [...msg.tool_calls, {
            name: (data as { tool_name?: string }).tool_name || '',
            id: (data as { tool_call_id?: string }).tool_call_id || '',
          }],
        }));
      });

      // 监听 session-message-saved（最终消息）
      stream.on('session:message:saved', (data) => {
        const savedMsg = data.message as unknown as SessionMessage;
        if (savedMsg) {
          onMessageSaved?.(savedMsg);
          // 替换占位消息
          onUpdateLastAssistant?.(() => savedMsg);
        }
      });

      // 监听任务完成
      stream.on('task:completed', () => {
        setState(prev => ({
          ...prev,
          isStreaming: false,
          currentPhase: 'complete',
          currentTaskId: null,
        }));
        disconnectStream();
      });

      // 监听任务失败
      stream.on('task:failed', (data) => {
        const errorMsg = (data as { error?: string }).error || '任务执行失败';
        setState(prev => ({
          ...prev,
          isStreaming: false,
          error: errorMsg,
          currentTaskId: null,
        }));
        onUpdateLastAssistant?.(msg => ({
          ...msg,
          status: 'error',
          error: errorMsg,
        }));
        disconnectStream();
      });

      stream.connect();
    } catch (err: unknown) {
      const errorMessage = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail || '发送消息失败';
      setState(prev => ({
        ...prev,
        isSending: false,
        isStreaming: false,
        error: errorMessage,
      }));
    }
  }, [agentId, sessionId, onAppendMessage, onUpdateLastAssistant, onMessageSaved, disconnectStream]);

  /**
   * 取消当前执行中的任务
   */
  const cancelExecution = useCallback(async () => {
    if (!state.currentTaskId) return;
    try {
      await taskApi.cancelTask(state.currentTaskId);
      disconnectStream();
      setState(prev => ({
        ...prev,
        isStreaming: false,
        currentTaskId: null,
        currentPhase: 'idle',
      }));
    } catch (err: unknown) {
      console.error('Cancel failed:', err);
    }
  }, [state.currentTaskId, disconnectStream]);

  // 组件卸载时断开连接
  useEffect(() => {
    return () => {
      disconnectStream();
    };
  }, [disconnectStream]);

  return {
    ...state,
    sendMessage,
    cancelExecution,
  };
};
