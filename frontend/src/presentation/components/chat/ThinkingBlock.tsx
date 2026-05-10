/**
 * 演示层 - 思考内容展示组件
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

// 简单的 SVG 图标组件
function SparklesIcon() {
  return (
    <svg className="w-4 h-4 text-purple-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M12 3l1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5L12 3z" />
      <path d="M5 19l1 3 1-3 3-1-3-1-1-3-1 3-3 1 3 1z" />
      <path d="M19 13l1 2 1-2 2-1-2-1-1-2-1 2-2 1 2 1z" />
    </svg>
  );
}

function ChevronDownIcon() {
  return (
    <svg className="w-4 h-4 ml-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M6 9l6 6 6-6" />
    </svg>
  );
}

function ChevronUpIcon() {
  return (
    <svg className="w-4 h-4 ml-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M18 15l-6-6-6 6" />
    </svg>
  );
}

export function ThinkingBlock({ content, isStreaming = false, onComplete }: ThinkingBlockProps) {
  const [isExpanded, setIsExpanded] = useState(true);
  const [prevContent, setPrevContent] = useState('');
  const contentEndRef = useRef<HTMLDivElement>(null);
  
  // 自动滚动到底部（流式显示时）
  useEffect(() => {
    if (isStreaming && isExpanded && contentEndRef.current) {
      contentEndRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, [content, isStreaming, isExpanded]);
  
  // 思考完毕后自动折叠
  useEffect(() => {
    if (!isStreaming && content && prevContent && content === prevContent) {
      // 内容不再变化，说明思考已完成
      const timer = setTimeout(() => {
        setIsExpanded(false);
        onComplete?.();
      }, 1500); // 思考完成后 1.5 秒自动折叠
      
      return () => clearTimeout(timer);
    }
    setPrevContent(content);
  }, [content, isStreaming, prevContent, onComplete]);
  
  if (!content) return null;
  
  return (
    <div className="my-3 rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 overflow-hidden">
      {/* 标题栏 */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center gap-2 px-4 py-2.5 text-sm font-medium text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700/50 transition-colors"
      >
        <SparklesIcon />
        <span>深度思考</span>
        {isStreaming && (
          <span className="ml-auto text-xs text-purple-500 animate-pulse">思考中...</span>
        )}
        {!isStreaming && content && (
          <span className="ml-auto text-xs text-gray-500">
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
        <div className="px-4 pb-3 text-sm text-gray-700 dark:text-gray-300 leading-relaxed whitespace-pre-wrap border-t border-gray-200 dark:border-gray-700">
          {content}
          <div ref={contentEndRef} />
        </div>
      )}
      
      {/* 折叠状态下的预览 */}
      {!isExpanded && content && (
        <div className="px-4 pb-2 text-xs text-gray-500 dark:text-gray-500">
          思考内容已折叠，共 {content.length} 字符
        </div>
      )}
    </div>
  );
}
