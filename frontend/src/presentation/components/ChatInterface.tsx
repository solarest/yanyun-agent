/**
 * 表现层 - 聊天界面组件
 */
import React, { useRef, useEffect } from 'react';
import type { ToolCallData } from '../../application/services/useAgentService';

interface ChatInterfaceProps {
  llmOutput: string;
  toolCalls: ToolCallData[];
  currentPhase: string;
  isConnected: boolean;
  taskStatus: string;
}

const phaseLabels: Record<string, string> = {
  idle: '空闲',
  thinking: '思考中',
  tool_executing: '工具执行中',
  loop_correcting: '循环纠正中',
  stuck_recovering: '恢复中',
  context_compacting: '上下文压缩中',
  complete: '完成',
  failed: '失败',
  cancelled: '已取消',
};

export const ChatInterface: React.FC<ChatInterfaceProps> = ({
  llmOutput,
  toolCalls,
  currentPhase,
  isConnected,
  taskStatus,
}) => {
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // 自动滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [llmOutput, toolCalls]);

  return (
    <div className="flex h-full flex-col">
      {/* 状态栏 */}
      <div className="flex items-center gap-2 border-b px-4 py-2">
        {isConnected && (
          <div className="flex items-center gap-2">
            <div className="h-2 w-2 animate-pulse rounded-full bg-success" />
            <span className="text-xs text-muted-foreground">
              {phaseLabels[currentPhase] || currentPhase}
            </span>
          </div>
        )}
        {taskStatus === 'completed' && (
          <div className="flex items-center gap-2">
            <div className="h-2 w-2 rounded-full bg-success" />
            <span className="text-xs text-success-foreground">已完成</span>
          </div>
        )}
        {taskStatus === 'failed' && (
          <div className="flex items-center gap-2">
            <div className="h-2 w-2 rounded-full bg-destructive" />
            <span className="text-xs text-destructive-foreground">失败</span>
          </div>
        )}
        {taskStatus === 'cancelled' && (
          <div className="flex items-center gap-2">
            <div className="h-2 w-2 rounded-full bg-muted-foreground" />
            <span className="text-xs text-muted-foreground">已取消</span>
          </div>
        )}
      </div>

      {/* 消息区域 */}
      <div className="flex-1 overflow-y-auto p-4">
        {/* LLM 输出 */}
        {llmOutput && (
          <div className="mb-4">
            <div className="mb-2 text-xs font-medium text-muted-foreground">
              Agent 回复
            </div>
            <div className="whitespace-pre-wrap rounded-lg border bg-card p-4 font-mono text-sm">
              {llmOutput}
            </div>
          </div>
        )}

        {/* 工具调用 */}
        {toolCalls.length > 0 && (
          <div className="mb-4">
            <div className="mb-2 text-xs font-medium text-muted-foreground">
              工具调用
            </div>
            <div className="space-y-2">
              {toolCalls.map((tool, index) => (
                <div
                  key={index}
                  className="rounded-lg border bg-card p-3"
                >
                  <div className="mb-1 flex items-center justify-between">
                    <span className="text-sm font-medium">
                      {tool.tool_name}
                    </span>
                    {tool.status && (
                      <span className="text-xs text-muted-foreground">
                        {tool.status}
                      </span>
                    )}
                  </div>
                  {tool.result && (
                    <div className="mt-2 rounded bg-muted p-2 font-mono text-xs">
                      {tool.result}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 空状态 */}
        {!llmOutput && toolCalls.length === 0 && (
          <div className="flex h-full items-center justify-center">
            <div className="text-center">
              <div className="text-lg font-medium text-muted-foreground">
                等待 Agent 响应
              </div>
              <div className="mt-1 text-sm text-muted-foreground">
                {isConnected ? 'Agent 正在处理任务...' : '创建 Agent 开始对话'}
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>
    </div>
  );
};
