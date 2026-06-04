/**
 * 表现层 - 工具调用组（内敛折叠容器）
 *
 * 与 ThinkingBlock 统一的内敛风格：
 * - 折叠态仅一行轻量提示
 * - 展开态左边框线 + 工具卡片列表
 * - 低对比度配色
 */
import React, { useState, useEffect, useCallback } from 'react';
import { ToolCallCard } from './ToolCallCard';

interface ToolTimelineItem {
  key: string;
  name: string;
  status: string;
  result?: string;
  input?: Record<string, unknown>;
  args?: Record<string, unknown>;
}

interface ToolCallGroupProps {
  items: ToolTimelineItem[];
  isStreaming?: boolean;
}

export const ToolCallGroup: React.FC<ToolCallGroupProps> = ({
  items,
  isStreaming = false,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const count = items.length;

  // 流式完成后自动折叠
  useEffect(() => {
    if (!isStreaming && count > 0) {
      setIsExpanded(false);
    }
  }, [isStreaming, count]);

  const handleToggle = useCallback(() => {
    setIsExpanded((prev) => !prev);
  }, []);

  if (count === 0) return null;

  // 统计完成/运行中/失败数量
  const doneCount = items.filter(i => i.status === 'success' || i.status === 'completed').length;
  const runningCount = items.filter(i => i.status === 'running').length;
  const failedCount = items.filter(i => i.status === 'error' || i.status === 'failed').length;

  const statusSummary = [
    runningCount > 0 ? `${runningCount} 执行中` : '',
    doneCount > 0 ? `${doneCount} 完成` : '',
    failedCount > 0 ? `${failedCount} 失败` : '',
  ].filter(Boolean).join(' · ');

  return (
    <div className="my-2">
      {/* 折叠态 */}
      {!isExpanded ? (
        <button
          onClick={handleToggle}
          className="flex items-center gap-1.5 text-xs text-muted-foreground/60 hover:text-muted-foreground transition-colors"
        >
          <span className="inline-block w-1 h-1 rounded-full bg-muted-foreground/40" />
          <span>工具调用 · {count} 个步骤</span>
          {statusSummary && (
            <span className="text-muted-foreground/40">({statusSummary})</span>
          )}
          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>
      ) : (
        /* 展开态 */
        <div className="border-l-2 border-muted-foreground/20 pl-3">
          {/* 标题行 */}
          <button
            onClick={handleToggle}
            className="flex items-center gap-1.5 text-xs text-muted-foreground/70 hover:text-muted-foreground transition-colors mb-1.5"
          >
            <span className="inline-block w-1 h-1 rounded-full bg-muted-foreground/40" />
            <span>工具调用 · {count} 个步骤</span>
            <svg className="w-3 h-3 rotate-180" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>

          {/* 工具卡片列表 */}
          <div className="space-y-1">
            {items.map((item) => (
              <ToolCallCard
                key={item.key}
                name={item.name}
                status={item.status}
                result={item.result}
                input={item.input}
                args={item.args}
                isStreaming={isStreaming}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
