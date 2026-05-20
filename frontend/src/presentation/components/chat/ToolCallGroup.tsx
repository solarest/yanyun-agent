/**
 * 表现层 - 工具调用组（外层折叠容器）
 * 
 * 功能：
 * - 显示"查看 x 个步骤"的折叠按钮
 * - 点击后展开显示所有工具调用卡片
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

  // 流式运行时默认展开，完成时自动折叠
  useEffect(() => {
    if (!isStreaming && count > 0) {
      setIsExpanded(false);
    }
  }, [isStreaming, count]);

  const handleToggle = useCallback(() => {
    setIsExpanded((prev) => !prev);
  }, []);

  if (count === 0) {
    return null;
  }

  return (
    <div className="rounded-lg border border-border/40 bg-background overflow-hidden">
      {/* 外层折叠按钮 */}
      <button
        onClick={handleToggle}
        className="w-full flex items-center gap-2 px-4 py-3 transition-colors cursor-pointer hover:bg-muted/30 text-left"
      >
        {/* 工具图标 */}
        <svg className="h-4 w-4 text-muted-foreground" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
        </svg>

        {/* 显示步骤数量 */}
        <span className="text-xs text-muted-foreground">
          查看 {count} 个步骤
        </span>

        {/* 展开箭头 */}
        <svg
          className={`ml-auto h-4 w-4 text-muted-foreground/60 transition-transform duration-200 ${
            isExpanded ? 'rotate-180' : ''
          }`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* 展开的内容区域 */}
      <div
        className={`overflow-hidden transition-all duration-200 ${
          isExpanded ? 'max-h-[2000px]' : 'max-h-0'
        }`}
      >
        <div className="border-t border-border/40">
          <div className="p-3 space-y-2">
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
      </div>
    </div>
  );
};
