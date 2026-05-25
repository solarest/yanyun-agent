/**
 * 表现层 - 消息气泡（时间线布局）
 */
import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { SessionMessage } from '@domain/entities/session';
import { ClarifyCard } from './ClarifyCard';
import { MultiClarifyCard, parseAllClarifyPrompts } from './MultiClarifyCard';
import { ToolCallGroup } from './ToolCallGroup';
import { ThinkingBlock } from './ThinkingBlock';

interface MessageBubbleProps {
  message: SessionMessage;
  embeddedSubAgents?: SessionMessage[];
  clarifyDisabled?: boolean;
  onClarifyAnswer?: (answer: string) => void;
}

const SPECIAL_TOOL_NAMES = new Set(['plan', 'plan_execute', 'plan_update', 'clarify']);

const isSpecialTool = (toolName: string): boolean => SPECIAL_TOOL_NAMES.has(toolName);

type VisibleToolCall = SessionMessage['tool_calls'][number];
type VisibleToolResult = SessionMessage['tool_results'][number];

interface ToolTimelineItem {
  key: string;
  name: string;
  status: string;
  result?: string;
  input?: Record<string, unknown>;
  args?: Record<string, unknown>;
}

const buildToolTimeline = (
  calls: VisibleToolCall[],
  results: VisibleToolResult[],
): ToolTimelineItem[] => {
  const usedResultIndexes = new Set<number>();

  const items: ToolTimelineItem[] = calls.map((call, index) => {
    const exactIndex = results.findIndex(
      (result, resultIndex) =>
        !usedResultIndexes.has(resultIndex) &&
        !!call.id &&
        result.id === call.id,
    );
    const fallbackIndex =
      exactIndex >= 0
        ? exactIndex
        : results.findIndex(
            (result, resultIndex) =>
              !usedResultIndexes.has(resultIndex) &&
              result.tool_name === call.name,
          );
    const result = fallbackIndex >= 0 ? results[fallbackIndex] : undefined;
    if (fallbackIndex >= 0) usedResultIndexes.add(fallbackIndex);

    return {
      key: call.id || `${call.name}-${index}`,
      name: call.name,
      status: result?.status || 'running',
      result: result?.result,
      input: call.input,
      args: call.args,
    };
  });

  results.forEach((result, index) => {
    if (usedResultIndexes.has(index)) return;
    items.push({
      key: result.id || `${result.tool_name}-result-${index}`,
      name: result.tool_name,
      status: result.status || 'success',
      result: result.result,
    });
  });

  return items;
};

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

/** 时间线圆点组件 */
const TimelineDot: React.FC<{ variant: 'user' | 'assistant' | 'error' | 'thinking' }> = ({ variant }) => {
  const colorMap = {
    user: 'bg-primary ring-primary/20',
    assistant: 'bg-muted-foreground/30 ring-muted-foreground/10',
    error: 'bg-destructive ring-destructive/20',
    thinking: 'bg-purple-400 ring-purple-200',
  };

  return (
    <div className="flex flex-col items-center w-6 shrink-0 pt-[6px]">
      <div className={`relative z-10 w-2.5 h-2.5 rounded-full ring-4 ring-background ${colorMap[variant]}`} />
    </div>
  );
};

export const MessageBubble: React.FC<MessageBubbleProps> = ({
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
  const displayContent = content;
  const subAgentLabel = isSubAgent
    ? message.meta?.stepId
      ? `Plan ${message.meta.stepId}`
      : 'Sub-agent'
    : null;
  const showSubAgentBody = !isSubAgent || isSubAgentExpanded;
  const subAgentStatusLabel = isStreaming ? '运行中' : isError ? '失败' : '完成';

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
        <TimelineDot variant="assistant" />
        <div className="flex-1 min-w-0 pt-0">
          <MultiClarifyCard
            content={message.content}
            disabled={clarifyDisabled || !onClarifyAnswer}
            timestamp={message.created_at}
            onAnswer={(answers: string[]) => {
              setClarifySubmitted(true);
              onClarifyAnswer?.(answers.join('\n'));
            }}
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
        <TimelineDot variant="assistant" />
        <div className="flex-1 min-w-0 pt-0">
          <ClarifyCard
            prompt={clarifyPrompt}
            disabled={clarifyDisabled || !onClarifyAnswer}
            timestamp={message.created_at}
            onAnswer={(answer: string) => {
              setClarifySubmitted(true);
              onClarifyAnswer?.(answer);
            }}
          />
          {timestamp}
        </div>
      </div>
    );
  }

  return (
    <div className="relative flex gap-3 pb-5 group">
      <TimelineDot variant={dotVariant} />

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

          {/* 工具调用摘要 */}
          {!isUser && showSubAgentBody && hasVisibleTools && (
            <div className="mb-2">
              <ToolCallGroup
                items={toolTimeline}
                isStreaming={isStreaming}
              />
            </div>
          )}

          {!isUser && !isSubAgent && embeddedSubAgents.length > 0 && (
            <EmbeddedSubAgentList messages={embeddedSubAgents} />
          )}

          {/* 深度思考内容 */}
          {!isUser && showSubAgentBody && hasThinking && (
            <ThinkingBlock
              content={message.thinking_content || ''}
              isStreaming={Boolean(isThinking)}
            />
          )}

          {!isUser && showSubAgentBody && clarifyPrompt && !clarifySubmitted && (
            <div className={hasVisibleTools ? 'mt-2' : ''}>
              <ClarifyCard
                prompt={clarifyPrompt}
                disabled={clarifyDisabled || !onClarifyAnswer}
                timestamp={message.created_at}
                onAnswer={(answer: string) => {
                  setClarifySubmitted(true);
                  onClarifyAnswer?.(answer);
                }}
              />
            </div>
          )}

          {/* 消息内容 */}
          {showSubAgentBody && (displayContent.trim() || isStreaming || !clarifyPrompt) && (
            <div className="markdown-content text-sm leading-relaxed">
              {displayContent ? (
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {displayContent}
                </ReactMarkdown>
              ) : (
                <>
                  {isStreaming ? '' : '...'}
                  {isStreaming && !displayContent && (
                    <span className="inline-block h-4 w-1 animate-pulse bg-current" />
                  )}
                </>
              )}
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
