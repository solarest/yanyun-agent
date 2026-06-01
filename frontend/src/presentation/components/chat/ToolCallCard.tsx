/**
 * 表现层 - 工具调用卡片（内敛风格）
 *
 * 与 ThinkingBlock 统一的内敛设计：
 * - 单行显示工具名 + 状态指示 + 展开箭头
 * - 展开后显示参数和结果
 * - 无卡片背景，仅左边框线分隔层级
 */
import React, { useState, useEffect, useCallback } from 'react';

interface ToolCallCardProps {
  name: string;
  status: string;
  result?: string;
  input?: Record<string, unknown>;
  args?: Record<string, unknown>;
  isStreaming?: boolean;
}

export const ToolCallCard: React.FC<ToolCallCardProps> = ({
  name,
  status,
  result,
  input,
  args,
  isStreaming = false,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);

  useEffect(() => {
    if (!isStreaming && (status === 'success' || status === 'completed')) {
      setIsExpanded(false);
    }
  }, [status, isStreaming]);

  const handleToggle = useCallback(() => {
    setIsExpanded((prev) => !prev);
  }, []);

  const isSuccess = status === 'success' || status === 'completed';
  const isError = status === 'error' || status === 'failed';
  const isRunning = status === 'running' || !status;
  const hasParams = (input && Object.keys(input).length > 0) || (args && Object.keys(args).length > 0);
  const hasResult = result && result.trim();
  const hasContent = hasParams || hasResult;

  const params = input || args;
  const paramsJson = hasParams ? JSON.stringify(params, null, 2) : null;

  return (
    <div className="text-xs">
      {/* 工具名称行 */}
      <button
        onClick={handleToggle}
        disabled={!hasContent}
        className={`w-full flex items-center gap-1.5 py-0.5 text-left transition-colors ${
          !hasContent ? 'cursor-default' : 'cursor-pointer hover:text-foreground'
        }`}
      >
        {/* 状态点 */}
        <span
          className={`inline-block w-1.5 h-1.5 rounded-full shrink-0 ${
            isRunning ? 'bg-blue-400 animate-pulse' :
            isSuccess ? 'bg-emerald-400' :
            isError ? 'bg-red-400' :
            'bg-muted-foreground/30'
          }`}
        />

        {/* 工具名 */}
        <span className="text-muted-foreground/80 min-w-0 truncate">{name}</span>

        {/* 状态文本 */}
        <span className="text-muted-foreground/40 shrink-0">
          {isRunning ? '执行中' : isSuccess ? '' : isError ? '失败' : ''}
        </span>

        {/* 展开箭头 */}
        {hasContent && (
          <svg
            className={`ml-auto h-3 w-3 shrink-0 text-muted-foreground/40 transition-transform duration-150 ${
              isExpanded ? 'rotate-180' : ''
            }`}
            fill="none" stroke="currentColor" viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        )}
      </button>

      {/* 展开内容 */}
      {hasContent && isExpanded && (
        <div className="ml-3.5 pl-3 border-l border-muted-foreground/15 space-y-1.5 mt-1 mb-1.5">
          {hasParams && (
            <pre className="text-[11px] font-mono text-muted-foreground/60 whitespace-pre-wrap break-all leading-relaxed">
              {paramsJson}
            </pre>
          )}
          {hasResult && (
            <div className="max-h-60 overflow-y-auto whitespace-pre-wrap text-[11px] font-mono text-muted-foreground/70 leading-relaxed">
              {result}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
