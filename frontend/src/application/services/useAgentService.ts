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

export interface LLMChunk {
  content: string;
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

    // 监听 LLM 流式输出
    stream.on('llm:chunk', (data) => {
      const chunk = data as unknown as LLMChunk;
      setLlmOutput(prev => prev + chunk.content);
    });

    // 监听 LLM 完成
    stream.on('llm:complete', () => {
      // LLM 调用完成
    });

    // 监听阶段变化
    stream.on('phase:changed', (data) => {
      setCurrentPhase(data.new_phase as string);
    });

    // 监听工具调用
    stream.on('tool:call', (data) => {
      const toolCall = data as unknown as ToolCallData;
      setToolCalls(prev => [...prev, toolCall]);
    });

    // 监听工具结果
    stream.on('tool:result', (data) => {
      const toolResult = data as unknown as ToolCallData;
      setToolCalls(prev => {
        const updated = [...prev];
        const lastIndex = updated.length - 1;
        if (lastIndex >= 0 && updated[lastIndex].tool_name === toolResult.tool_name) {
          updated[lastIndex] = { ...updated[lastIndex], ...toolResult };
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
