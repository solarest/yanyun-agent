/**
 * 表现层 - 工具调用卡片（时间线嵌套展开样式）
 *
 * 结构：
 * 第一层：工具名 + 状态 + 展开箭头
 * 第二层：参数（如果有）
 * 第三层：嵌套结果（如果有）
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
    <div className="rounded-xl border border-border/30 bg-muted/20 overflow-hidden">
      {/* 第一层：工具名 + 状态 + 展开箭头 */}
      <button
        onClick={handleToggle}
        disabled={!hasContent}
        className={`w-full flex items-center gap-2 px-3 py-2 transition-colors text-left ${
          !hasContent ? 'cursor-default' : 'cursor-pointer hover:bg-muted/40'
        }`}
      >
        {/* 状态图标 */}
        <div className="flex items-center justify-center w-4 h-4 shrink-0">
          {isRunning && (
            <svg className="h-3.5 w-3.5 animate-spin text-blue-500" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
            </svg>
          )}
          {isSuccess && (
            <svg className="h-3.5 w-3.5 text-emerald-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          )}
          {isError && (
            <svg className="h-3.5 w-3.5 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          )}
        </div>

        {/* 工具名称 */}
        <span className="text-xs text-muted-foreground">{name}</span>

        {/* 右侧展开箭头 */}
        {hasContent && (
          <svg
            className={`ml-auto h-3.5 w-3.5 text-muted-foreground/50 transition-transform duration-200 ${
              isExpanded ? 'rotate-180' : ''
            }`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        )}
      </button>

      {/* 第二层和第三层：嵌套内容 */}
      {hasContent && (
        <div
          className={`overflow-hidden transition-all duration-200 ${
            isExpanded ? 'max-h-[800px]' : 'max-h-0'
          }`}
        >
          <div className="border-t border-border/20">
            {hasParams && (
              <div className="px-3 py-2.5 bg-muted/10 border-b border-border/20">
                <pre className="text-xs font-mono text-muted-foreground whitespace-pre-wrap break-all">
                  {paramsJson}
                </pre>
              </div>
            )}

            {hasResult && (
              <div className="px-3 py-2.5">
                <div className="max-h-80 overflow-y-auto whitespace-pre-wrap rounded-lg bg-muted/20 px-3 py-2.5 text-xs font-mono text-muted-foreground border border-border/30">
                  {result}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
