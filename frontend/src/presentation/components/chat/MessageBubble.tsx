/**
 * 表现层 - 消息气泡
 */
import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { SessionMessage } from '@domain/entities/session';
import { ClarifyCard } from './ClarifyCard';
import { MultiClarifyCard, parseAllClarifyPrompts } from './MultiClarifyCard';
import { ToolCallCard } from './ToolCallCard';

interface MessageBubbleProps {
  message: SessionMessage;
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

export const MessageBubble: React.FC<MessageBubbleProps> = ({
  message,
  clarifyDisabled = false,
  onClarifyAnswer,
}) => {
  const [clarifySubmitted, setClarifySubmitted] = useState(false);
  const isUser = message.role === 'user';
  const isError = message.status === 'error';
  const isStreaming = message.status === 'streaming';
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
  const subAgentLabel = message.meta?.isSubAgent
    ? `Plan ${message.meta.stepId || '?'}`
    : null;

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
          <div className="mb-2 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
            {subAgentLabel}
            {message.meta?.title ? ` · ${message.meta.title}` : ' · Sub-agent'}
          </div>
        )}

        {/* 工具调用摘要 */}
        {!isUser && hasVisibleTools && (
          <div className="mb-2 space-y-2 border-b border-border/50 pb-2">
            {toolTimeline.map((item) => (
              <ToolCallCard
                key={item.key}
                name={item.name}
                status={item.status}
                result={item.result}
                isStreaming={isStreaming}
              />
            ))}
          </div>
        )}

        {!isUser && clarifyPrompt && !clarifySubmitted && (
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
        {(displayContent.trim() || isStreaming || !clarifyPrompt) && (
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
        {isError && message.error && (
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
