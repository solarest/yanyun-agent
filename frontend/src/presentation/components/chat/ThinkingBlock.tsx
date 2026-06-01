/**
 * 表现层 - 思考内容展示组件（内敛风格）
 *
 * 展示 LLM 的深度思考过程，参考 ChatGPT/Claude 的内敛设计：
 * - 流式时自动展开，完成后自动折叠
 * - 低对比度配色，减少视觉干扰
 * - 折叠态仅显示一行轻量提示
 */
import { useState, useEffect, useRef } from 'react';

interface ThinkingBlockProps {
  content: string;
  isStreaming?: boolean;
  onComplete?: () => void;
}

export function ThinkingBlock({ content, isStreaming = false, onComplete }: ThinkingBlockProps) {
  const [isExpanded, setIsExpanded] = useState(true);
  const [prevContent, setPrevContent] = useState('');
  const contentEndRef = useRef<HTMLDivElement>(null);

  const chars = content.length;

  // 流式时自动滚到底部
  useEffect(() => {
    if (isStreaming && isExpanded && contentEndRef.current) {
      contentEndRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, [content, isStreaming, isExpanded]);

  // 流式完成后自动折叠
  useEffect(() => {
    if (!isStreaming && content && prevContent && content === prevContent) {
      const timer = setTimeout(() => {
        setIsExpanded(false);
        onComplete?.();
      }, 1200);
      return () => clearTimeout(timer);
    }
    setPrevContent(content);
  }, [content, isStreaming, prevContent, onComplete]);

  if (!content) return null;

  return (
    <div className="my-2">
      {/* 折叠态 —— 仅一行轻量提示 */}
      {!isExpanded ? (
        <button
          onClick={() => setIsExpanded(true)}
          className="flex items-center gap-1.5 text-xs text-muted-foreground/60 hover:text-muted-foreground transition-colors"
        >
          <span className="inline-block w-1 h-1 rounded-full bg-muted-foreground/40" />
          <span>思考过程 ({chars} 字符)</span>
          <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>
      ) : (
        /* 展开态 */
        <div className="border-l-2 border-muted-foreground/20 pl-3">
          {/* 标题行 */}
          <button
            onClick={() => setIsExpanded(false)}
            className="flex items-center gap-1.5 text-xs text-muted-foreground/70 hover:text-muted-foreground transition-colors mb-1.5"
          >
            {isStreaming ? (
              <>
                <span className="inline-block w-1.5 h-1.5 rounded-full bg-muted-foreground/50 animate-pulse" />
                <span>思考中…</span>
              </>
            ) : (
              <>
                <span className="inline-block w-1 h-1 rounded-full bg-muted-foreground/40" />
                <span>思考过程</span>
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 15l6-6 6 6" />
                </svg>
              </>
            )}
          </button>

          {/* 思考内容 */}
          <div className="text-sm text-muted-foreground/80 leading-relaxed whitespace-pre-wrap">
            {content}
            <div ref={contentEndRef} />
          </div>
        </div>
      )}
    </div>
  );
}
