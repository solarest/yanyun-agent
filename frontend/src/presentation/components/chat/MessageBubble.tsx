/**
 * 表现层 - 消息气泡（时间线布局）
 *
 * 展示职责拆分为：
 * - MessageTimeline：segments 时间线渲染
 * - ToolTimeline：tool_calls/tool_results 合并（纯函数）
 * 本组件负责消息骨架（头像、子代理折叠、clarify 早退分支、旧布局回退）。
 *
 * 使用 React.memo：流式期间每 token 更新只重渲染目标消息，
 * 历史消息因 props 引用稳定而跳过渲染（依赖 MessageList 传入稳定引用）。
 */
import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { SessionMessage } from '@domain/entities/session';
import { ClarifyCard } from './ClarifyCard';
import { MultiClarifyCard, parseAllClarifyPrompts } from './MultiClarifyCard';
import { ToolCallGroup } from './ToolCallGroup';
import { ThinkingBlock } from './ThinkingBlock';
import { MessageTimeline } from './MessageTimeline';
import { buildToolTimeline, isSpecialTool } from './ToolTimeline';

interface MessageBubbleProps {
  message: SessionMessage;
  /** 内嵌子代理消息；仅父消息存在时传入（undefined 保证 memo 浅比较稳定） */
  embeddedSubAgents?: SessionMessage[];
  clarifyDisabled?: boolean;
  onClarifyAnswer?: (answer: string) => void;
}

interface EmbeddedSubAgentListProps {
  messages: SessionMessage[];
}

const EmbeddedSubAgentList: React.FC<EmbeddedSubAgentListProps> = ({ messages }) => {
  const [expandedIds, setExpandedIds] = useState<Set<string>>(() => new Set());

  if (messages.length === 0) return null;

  const toggle = (messageId: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(messageId)) {
        next.delete(messageId);
      } else {
        next.add(messageId);
      }
      return next;
    });
  };

  return (
    <div className="mb-3 overflow-hidden rounded-xl border border-border/40 bg-muted/30">
      <div className="border-b border-border/30 px-3 py-2 text-xs font-medium text-muted-foreground">
        Sub-agents · {messages.length}
      </div>
      <div className="divide-y divide-border/20">
        {messages.map((subMessage) => {
          const isExpanded = expandedIds.has(subMessage.id);
          const isError = subMessage.status === 'error';
          const isStreaming = subMessage.status === 'streaming';
          const dotColor = isStreaming ? 'bg-blue-500' : isError ? 'bg-destructive' : 'bg-emerald-500';
          const toolTimeline = buildToolTimeline(
            subMessage.tool_calls.filter((tc) => !isSpecialTool(tc.name)),
            subMessage.tool_results.filter((result) => !isSpecialTool(result.tool_name)),
          );
          const title = subMessage.meta?.title || 'Sub-agent';

          return (
            <div key={subMessage.id}>
              <button
                type="button"
                onClick={() => toggle(subMessage.id)}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-muted-foreground transition-colors hover:bg-muted/50 hover:text-foreground"
                aria-expanded={isExpanded}
              >
                <span className="min-w-0 flex-1 truncate">
                  Sub-agent · {title}
                </span>
                <span className={`w-2 h-2 rounded-full shrink-0 ring-2 ring-background ${dotColor}`} />
                <svg
                  className={`h-4 w-4 shrink-0 transition-transform duration-200 ${
                    isExpanded ? 'rotate-180' : ''
                  }`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>

              {isExpanded && (
                <div className="space-y-2 px-3 pb-3">
                  {toolTimeline.length > 0 && (
                    <ToolCallGroup
                      items={toolTimeline}
                      isStreaming={isStreaming}
                    />
                  )}
                  {subMessage.content.trim() && (
                    <div className="markdown-content text-xs leading-relaxed text-foreground">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {subMessage.content}
                      </ReactMarkdown>
                    </div>
                  )}
                  {isError && subMessage.error && (
                    <div className="text-xs text-destructive">
                      {subMessage.error}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

/** 头像组件 — 替代时间线圆点 */
const Avatar: React.FC<{ variant: 'user' | 'assistant' | 'error' }> = ({ variant }) => {
  if (variant === 'user') {
    return (
      <div className="flex-shrink-0 w-7 h-7 rounded-full bg-primary/10 border border-primary/20 flex items-center justify-center">
        <svg className="w-3.5 h-3.5 text-primary/70" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z" />
        </svg>
      </div>
    );
  }
  return (
    <div className={`flex-shrink-0 w-7 h-7 rounded-full border flex items-center justify-center ${
      variant === 'error'
        ? 'bg-destructive/10 border-destructive/20'
        : 'bg-muted border-border'
    }`}>
      <svg className={`w-3.5 h-3.5 ${variant === 'error' ? 'text-destructive/70' : 'text-muted-foreground'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth={2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 00-2.455 2.456z" />
      </svg>
    </div>
  );
};

const MessageBubbleInner: React.FC<MessageBubbleProps> = ({
  message,
  embeddedSubAgents = [],
  clarifyDisabled = false,
  onClarifyAnswer,
}) => {
  const [clarifySubmitted, setClarifySubmitted] = useState(false);
  const [isSubAgentExpanded, setIsSubAgentExpanded] = useState(false);
  const isUser = message.role === 'user';
  const isError = message.status === 'error';
  const isStreaming = message.status === 'streaming';
  const hasThinking = message.has_thinking && message.thinking_content;
  const isThinking = isStreaming && hasThinking;
  const isSubAgent = Boolean(message.meta?.isSubAgent);
  const visibleToolCalls = message.tool_calls.filter((tc) => !isSpecialTool(tc.name));
  const visibleToolResults = message.tool_results.filter(
    (result) => !isSpecialTool(result.tool_name),
  );

  const allClarifyPrompts = parseAllClarifyPrompts(message.content);
  const hasMultipleClarify = allClarifyPrompts.length > 1;
  const hasSingleClarify = allClarifyPrompts.length === 1;

  const clarifyPrompt = hasSingleClarify ? allClarifyPrompts[0] : null;
  const contentIsClarifyPrompt = hasSingleClarify || hasMultipleClarify;
  const content = contentIsClarifyPrompt ? '' : message.content;
  const toolTimeline = buildToolTimeline(visibleToolCalls, visibleToolResults);
  const hasVisibleTools = toolTimeline.length > 0;
  const subAgentLabel = isSubAgent
    ? message.meta?.stepId
      ? `Plan ${message.meta.stepId}`
      : 'Sub-agent'
    : null;
  const showSubAgentBody = !isSubAgent || isSubAgentExpanded;
  const subAgentStatusLabel = isStreaming ? '运行中' : isError ? '失败' : '完成';

  // clarify 回答统一入口：更新 submitted 状态后回调（与时间线内 clarify 卡片共享状态）
  const handleClarifyAnswer = (answer: string) => {
    setClarifySubmitted(true);
    onClarifyAnswer?.(answer);
  };

  const timestamp = (
    <div className="mt-1.5 pl-1 text-[10px] text-muted-foreground/50">
      {new Date(message.created_at).toLocaleTimeString()}
    </div>
  );

  const cardBorder = isUser
    ? 'border-primary/15 bg-primary/5'
    : isError
      ? 'border-destructive/20 bg-destructive/5'
      : 'border-border/50 bg-card';

  const dotVariant = isUser ? 'user' : isError ? 'error' : 'assistant';

  // 多个 clarify 问题：使用 MultiClarifyCard
  if (!isUser && hasMultipleClarify && !content.trim() && !hasVisibleTools && !clarifySubmitted) {
    return (
      <div className="relative flex gap-3 pb-5">
        <Avatar variant="assistant" />
        <div className="flex-1 min-w-0 pt-0">
          <MultiClarifyCard
            content={message.content}
            disabled={clarifyDisabled || !onClarifyAnswer}
            timestamp={message.created_at}
            onAnswer={(answers: string[]) => handleClarifyAnswer(answers.join('\n'))}
          />
          {timestamp}
        </div>
      </div>
    );
  }

  // 单个 clarify 问题：使用 ClarifyCard
  if (!isUser && clarifyPrompt && !content.trim() && !hasVisibleTools && !clarifySubmitted) {
    return (
      <div className="relative flex gap-3 pb-5">
        <Avatar variant="assistant" />
        <div className="flex-1 min-w-0 pt-0">
          <ClarifyCard
            prompt={clarifyPrompt}
            disabled={clarifyDisabled || !onClarifyAnswer}
            timestamp={message.created_at}
            onAnswer={handleClarifyAnswer}
          />
          {timestamp}
        </div>
      </div>
    );
  }

  return (
    <div className="relative flex gap-3 pb-5 group">
      <Avatar variant={dotVariant} />

      <div className="flex-1 min-w-0 pt-0">
        <div className={`rounded-2xl border px-4 py-3 ${cardBorder}`}>
          {!isUser && subAgentLabel && (
            <button
              type="button"
              onClick={() => setIsSubAgentExpanded((prev) => !prev)}
              className="mb-2 flex w-full items-center gap-2 text-left text-[11px] font-medium uppercase tracking-wide text-muted-foreground transition-colors hover:text-foreground"
              aria-expanded={isSubAgentExpanded}
            >
              <span className="min-w-0 flex-1 truncate">
                {subAgentLabel}
                {message.meta?.title ? ` · ${message.meta.title}` : ' · Sub-agent'}
              </span>
              <span className="shrink-0 normal-case tracking-normal">
                {subAgentStatusLabel}
              </span>
              <svg
                className={`h-4 w-4 shrink-0 transition-transform duration-200 ${
                  isSubAgentExpanded ? 'rotate-180' : ''
                }`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>
          )}

          {!isUser && !isSubAgent && embeddedSubAgents.length > 0 && (
            <EmbeddedSubAgentList messages={embeddedSubAgents} />
          )}

          {/* ── 时间线渲染：segments 可用时按实际事件顺序渲染，否则回退为旧布局 ── */}
          {!isUser && showSubAgentBody && (() => {
            const segments = message.segments;
            const hasSegments = segments && segments.length > 0;

            // 有 segments 时：按时间线顺序渲染
            if (hasSegments) {
              return (
                <MessageTimeline
                  segments={segments!}
                  isStreaming={isStreaming}
                  isThinking={Boolean(isThinking)}
                  createdAt={message.created_at}
                  taskId={message.task_id}
                  clarifyDisabled={clarifyDisabled}
                  clarifySubmitted={clarifySubmitted}
                  onClarifyAnswer={handleClarifyAnswer}
                />
              );
            }

            // 旧布局回退：固定分区渲染
            return (
              <>
                {hasVisibleTools && (
                  <div className="mb-2">
                    <ToolCallGroup
                      items={toolTimeline}
                      isStreaming={isStreaming}
                    />
                  </div>
                )}
                {hasThinking && (
                  <ThinkingBlock
                    content={message.thinking_content || ''}
                    isStreaming={Boolean(isThinking)}
                  />
                )}
                {clarifyPrompt && (
                  <div className={hasVisibleTools ? 'mt-2' : ''}>
                    <ClarifyCard
                      prompt={clarifyPrompt}
                      disabled={clarifyDisabled || !onClarifyAnswer}
                      submitted={clarifySubmitted}
                      timestamp={message.created_at}
                      onAnswer={handleClarifyAnswer}
                    />
                  </div>
                )}
                {(content.trim() || isStreaming || !clarifyPrompt) && (
                  <div className="markdown-content text-sm leading-relaxed">
                    {content ? (
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {content}
                      </ReactMarkdown>
                    ) : (
                      <>
                        {isStreaming ? '' : '...'}
                        {isStreaming && !content && (
                          <span className="inline-block h-4 w-1 animate-pulse bg-current" />
                        )}
                      </>
                    )}
                  </div>
                )}
              </>
            );
          })()}

          {/* 用户消息内容 */}
          {isUser && (
            <div className="text-sm leading-relaxed whitespace-pre-wrap">
              {message.content}
            </div>
          )}

          {/* 错误信息 */}
          {showSubAgentBody && isError && message.error && (
            <div className="mt-2 border-t border-destructive/20 pt-2 text-xs text-destructive">
              {message.error}
            </div>
          )}
        </div>

        {timestamp}
      </div>
    </div>
  );
};

export const MessageBubble = React.memo(MessageBubbleInner);
