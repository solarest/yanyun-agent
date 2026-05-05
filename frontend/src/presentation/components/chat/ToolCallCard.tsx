/**
 * 表现层 - 工具调用卡片
 */
import React, { useState, useEffect, useCallback } from 'react';

interface ToolCallCardProps {
  name: string;
  status: string;
  result?: string;
  isStreaming?: boolean;
}

export const ToolCallCard: React.FC<ToolCallCardProps> = ({
  name,
  status,
  result,
  isStreaming = false,
}) => {
  const [isCollapsed, setIsCollapsed] = useState(false);

  // 运行完成且成功时自动折叠（仅在非流式状态下）
  useEffect(() => {
    if (!isStreaming && (status === 'success' || status === 'completed')) {
      const timer = setTimeout(() => {
        setIsCollapsed(true);
      }, 500); // 延迟500ms折叠，让用户能看到结果
      return () => clearTimeout(timer);
    }
  }, [status, isStreaming]);

  const handleToggle = useCallback(() => {
    setIsCollapsed((prev) => !prev);
  }, []);

  const isSuccess = status === 'success' || status === 'completed';
  const isError = status === 'error' || status === 'failed';
  const isRunning = status === 'running' || !status;
  const hasResult = result && result.trim();

  return (
    <div
      className={`group rounded-lg border transition-all duration-200 ${
        isError
          ? 'border-destructive/30 bg-destructive/5'
          : isSuccess
            ? 'border-success/20 bg-success/5'
            : isRunning
              ? 'border-primary/20 bg-primary/5'
              : 'border-border/50 bg-accent/30'
      }`}
    >
      {/* 卡片头部 */}
      <button
        type="button"
        onClick={handleToggle}
        disabled={isRunning || !hasResult}
        className={`flex w-full items-center gap-3 px-3 py-2.5 text-xs transition-all ${
          isRunning || !hasResult
            ? 'cursor-default'
            : 'cursor-pointer hover:bg-accent/50'
        }`}
      >
        {/* 左侧：工具图标 + 名称 */}
        <div className="flex min-w-0 items-center gap-2.5 flex-1">
          {/* 状态指示点 */}
          <div className="relative flex h-6 w-6 shrink-0 items-center justify-center">
            <div
              className={`h-2 w-2 rounded-full ${
                isError
                  ? 'bg-destructive'
                  : isSuccess
                    ? 'bg-success'
                    : isRunning
                      ? 'bg-primary animate-pulse'
                      : 'bg-muted-foreground/40'
              }`}
            />
            {isRunning && (
              <div className="absolute inset-0 h-2 w-2 animate-ping rounded-full bg-primary/30" />
            )}
          </div>

          {/* 工具名称 */}
          <div className="flex items-center gap-2 min-w-0">
            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-muted text-[10px] font-mono text-muted-foreground">
              <svg
                className="h-3 w-3"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
                />
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                />
              </svg>
            </span>
            <span className="truncate font-semibold text-foreground">{name}</span>
          </div>
        </div>

        {/* 右侧：状态标签 + 展开/折叠指示器 */}
        <div className="flex shrink-0 items-center gap-2">
          {/* 状态标签 */}
          <span
            className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium transition-colors ${
              isError
                ? 'bg-destructive/10 text-destructive border border-destructive/20'
                : isSuccess
                  ? 'bg-success/10 text-success border border-success/20'
                  : isRunning
                    ? 'bg-primary/10 text-primary border border-primary/20'
                    : 'bg-muted text-muted-foreground border border-border'
            }`}
          >
            {isRunning && (
              <svg
                className="mr-1 h-3 w-3 animate-spin"
                fill="none"
                viewBox="0 0 24 24"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                />
              </svg>
            )}
            {isSuccess && (
              <svg
                className="mr-1 h-3 w-3"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M5 13l4 4L19 7"
                />
              </svg>
            )}
            {status}
          </span>

          {/* 展开/折叠指示器 */}
          {hasResult && !isRunning && (
            <svg
              className={`h-4 w-4 text-muted-foreground transition-transform duration-200 ${
                isCollapsed ? '' : 'rotate-180'
              }`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M19 9l-7 7-7-7"
              />
            </svg>
          )}
        </div>
      </button>

      {/* 卡片内容 - 可折叠区域 */}
      {hasResult && (
        <div
          className={`overflow-hidden transition-all duration-300 ease-in-out ${
            isCollapsed ? 'max-h-0' : 'max-h-96'
          }`}
        >
          <div className="border-t border-border/50 px-3 pb-3 pt-2">
            <div className="max-h-80 overflow-y-auto whitespace-pre-wrap rounded-md bg-background/80 px-3 py-2 text-xs font-mono text-muted-foreground border border-border/30">
              {result}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
