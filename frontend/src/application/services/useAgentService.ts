/**
 * 应用层 - Agent 服务 Hook (管理 SSE 事件流)
 */
import { useState, useCallback, useRef, useEffect } from 'react';
import { AgentEventStream } from '../../infrastructure/api/eventStream';

export interface AgentEvent {
  id: string;
  type: string;
  data: Record<string, unknown>;
  timestamp: string;
}

export interface ToolCallData {
  tool_name: string;
  tool_input: Record<string, unknown>;
  status?: string;
  result?: string;
}

export const useAgentService = (baseUrl: string) => {
  const [isConnected, setIsConnected] = useState(false);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [llmOutput, setLlmOutput] = useState('');
  const [currentPhase, setCurrentPhase] = useState<string>('idle');
  const [toolCalls, setToolCalls] = useState<ToolCallData[]>([]);
  const streamRef = useRef<AgentEventStream | null>(null);

  const connect = useCallback((taskId: string) => {
    // 断开之前的连接
    if (streamRef.current) {
      streamRef.current.disconnect();
    }

    // 重置状态
    setEvents([]);
    setLlmOutput('');
    setCurrentPhase('idle');
    setToolCalls([]);

    // 创建新连接
    const stream = new AgentEventStream(baseUrl, taskId);
    streamRef.current = stream;

    // 监听任务开始
    stream.on('task:started', () => {
      setIsConnected(true);
    });

    // 监听 LLM 流式输出（后端字段为 `text`）
    stream.on('llm:chunk', (data) => {
      setLlmOutput((prev) => prev + (data.text || ''));
    });

    // 监听 LLM 完成
    stream.on('llm:complete', () => {
      // LLM 调用完成
    });

    // 监听阶段变化（后端字段为 `phase`）
    stream.on('phase:changed', (data) => {
      setCurrentPhase(String(data.phase));
    });

    // 监听工具调用（后端字段为 toolName/input）
    stream.on('tool:call', (data) => {
      setToolCalls((prev) => [
        ...prev,
        { tool_name: data.toolName, tool_input: data.input },
      ]);
    });

    // 监听工具结果（合并到最后一条同名 toolCall）
    stream.on('tool:result', (data) => {
      setToolCalls((prev) => {
        const updated = [...prev];
        const lastIndex = updated.length - 1;
        if (lastIndex >= 0 && updated[lastIndex].tool_name === data.toolName) {
          updated[lastIndex] = {
            ...updated[lastIndex],
            status: data.status,
            result: data.output ?? data.error ?? '',
          };
        }
        return updated;
      });
    });

    // 监听任务完成
    stream.on('task:completed', () => {
      setIsConnected(false);
    });

    // 监听任务失败
    stream.on('task:failed', (data) => {
      setIsConnected(false);
      console.error('Task failed:', data);
    });

    // 连接
    stream.connect();
  }, [baseUrl]);

  const disconnect = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.disconnect();
      streamRef.current = null;
    }
    setIsConnected(false);
  }, []);

  // 组件卸载时断开连接
  useEffect(() => {
    return () => {
      disconnect();
    };
  }, [disconnect]);

  return {
    isConnected,
    events,
    llmOutput,
    currentPhase,
    toolCalls,
    connect,
    disconnect,
  };
};
