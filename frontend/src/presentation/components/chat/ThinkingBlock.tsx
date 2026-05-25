/**
 * 演示层 - 思考内容展示组件（时间线样式）
 *
 * 展示 LLM 的深度思考过程，支持：
 * - 流式显示思考内容
 * - 思考完毕后自动折叠
 * - 手动展开/收起
 */
import { useState, useEffect, useRef } from 'react';

interface ThinkingBlockProps {
  content: string;
  isStreaming?: boolean;
  onComplete?: () => void;
}

function SparklesIcon() {
  return (
    <svg className="w-3.5 h-3.5 text-purple-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M12 3l1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5L12 3z" />
      <path d="M5 19l1 3 1-3 3-1-3-1-1-3-1 3-3 1 3 1z" />
      <path d="M19 13l1 2 1-2 2-1-2-1-1-2-1 2-2 1 2 1z" />
    </svg>
  );
}

function ChevronDownIcon() {
  return (
    <svg className="w-3.5 h-3.5 ml-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M6 9l6 6 6-6" />
    </svg>
  );
}

function ChevronUpIcon() {
  return (
    <svg className="w-3.5 h-3.5 ml-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M18 15l-6-6-6 6" />
    </svg>
  );
}

export function ThinkingBlock({ content, isStreaming = false, onComplete }: ThinkingBlockProps) {
  const [isExpanded, setIsExpanded] = useState(true);
  const [prevContent, setPrevContent] = useState('');
  const contentEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isStreaming && isExpanded && contentEndRef.current) {
      contentEndRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, [content, isStreaming, isExpanded]);

  useEffect(() => {
    if (!isStreaming && content && prevContent && content === prevContent) {
      const timer = setTimeout(() => {
        setIsExpanded(false);
        onComplete?.();
      }, 1500);

      return () => clearTimeout(timer);
    }
    setPrevContent(content);
  }, [content, isStreaming, prevContent, onComplete]);

  if (!content) return null;

  return (
    <div className="my-3 rounded-xl border border-purple-200/60 dark:border-purple-500/20 bg-purple-50/50 dark:bg-purple-950/20 overflow-hidden">
      {/* 标题栏 */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center gap-2 px-3 py-2 text-sm font-medium text-purple-700 dark:text-purple-400 hover:bg-purple-100/50 dark:hover:bg-purple-900/20 transition-colors"
      >
        <SparklesIcon />
        <span>深度思考</span>
        {isStreaming && (
          <span className="ml-auto text-xs text-purple-500 animate-pulse">思考中...</span>
        )}
        {!isStreaming && content && (
          <span className="ml-auto text-xs text-muted-foreground">
            {isExpanded ? '点击收起' : '点击展开'}
          </span>
        )}
        {isExpanded ? (
          <ChevronUpIcon />
        ) : (
          <ChevronDownIcon />
        )}
      </button>

      {/* 思考内容 */}
      {isExpanded && (
        <div className="px-3 pb-2.5 text-sm text-foreground leading-relaxed whitespace-pre-wrap border-t border-purple-200/40 dark:border-purple-500/10">
          {content}
          <div ref={contentEndRef} />
        </div>
      )}

      {/* 折叠状态下的预览 */}
      {!isExpanded && content && (
        <div className="px-3 pb-2 text-xs text-muted-foreground">
          思考内容已折叠，共 {content.length} 字符
        </div>
      )}
    </div>
  );
}
