/**
 * 表现层 - 消息气泡
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
    <div className="mb-3 overflow-hidden rounded-lg border border-border/40 bg-background/70">
      <div className="border-b border-border/40 px-3 py-2 text-xs font-medium text-muted-foreground">
        Sub-agents · {messages.length}
      </div>
      <div className="divide-y divide-border/40">
        {messages.map((subMessage) => {
          const isExpanded = expandedIds.has(subMessage.id);
          const isError = subMessage.status === 'error';
          const isStreaming = subMessage.status === 'streaming';
          const statusLabel = isStreaming ? '运行中' : isError ? '失败' : '完成';
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
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-muted-foreground transition-colors hover:bg-muted/30 hover:text-foreground"
                aria-expanded={isExpanded}
              >
                <span className="min-w-0 flex-1 truncate">
                  Sub-agent · {title}
                </span>
                <span className={isError ? 'text-destructive' : ''}>
                  {statusLabel}
                </span>
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
  
  // 从 message.content 中解析所有 clarify 问题（后端已将多个 clarify 合并到 content）
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

  // 多个 clarify 问题：使用 MultiClarifyCard
  if (!isUser && hasMultipleClarify && !content.trim() && !hasVisibleTools && !clarifySubmitted) {
    return (
      <div className="flex justify-start">
        <MultiClarifyCard
          content={message.content}
          disabled={clarifyDisabled || !onClarifyAnswer}
          timestamp={message.created_at}
          onAnswer={(answers: string[]) => {
            // 将多个答案合并为一条消息发送
            setClarifySubmitted(true);
            onClarifyAnswer?.(answers.join('\n'));
          }}
        />
      </div>
    );
  }
  
  // 单个 clarify 问题：使用 ClarifyCard
  if (!isUser && clarifyPrompt && !content.trim() && !hasVisibleTools && !clarifySubmitted) {
    return (
      <div className="flex justify-start">
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
    );
  }

  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[75%] rounded-2xl px-4 py-2.5 ${
          isUser
            ? 'bg-primary text-primary-foreground'
            : isError
              ? 'border border-destructive bg-destructive/10 text-foreground'
              : 'bg-accent text-foreground'
        }`}
      >
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
          <div className="mt-2 border-t border-destructive/30 pt-2 text-xs text-destructive">
            {message.error}
          </div>
        )}

        {/* 时间戳 */}
        <div
          className={`mt-1 text-right text-[10px] ${
            isUser ? 'text-primary-foreground/60' : 'text-muted-foreground'
          }`}
        >
          {new Date(message.created_at).toLocaleTimeString()}
        </div>
      </div>
    </div>
  );
};
