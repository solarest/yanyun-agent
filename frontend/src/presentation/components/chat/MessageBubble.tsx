/**
 * 表现层 - 消息气泡
 */
import React from 'react';
import type { SessionMessage } from '@domain/entities/session';
import { ClarifyCard, parseClarifyPrompt } from './ClarifyCard';

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
  const isUser = message.role === 'user';
  const isError = message.status === 'error';
  const isStreaming = message.status === 'streaming';
  const visibleToolCalls = message.tool_calls.filter((tc) => !isSpecialTool(tc.name));
  const visibleToolResults = message.tool_results.filter(
    (result) => !isSpecialTool(result.tool_name),
  );
  const clarifyResult = message.tool_results.find(
    (result) => result.tool_name === 'clarify',
  );
  const clarifyPrompt =
    parseClarifyPrompt(clarifyResult?.result) || parseClarifyPrompt(message.content);
  const contentIsClarifyPrompt = !!parseClarifyPrompt(message.content);
  const content = contentIsClarifyPrompt ? '' : message.content;
  const toolTimeline = buildToolTimeline(visibleToolCalls, visibleToolResults);
  const hasVisibleTools = toolTimeline.length > 0;
  const displayContent = content;

  if (!isUser && clarifyPrompt && !content.trim() && !hasVisibleTools) {
    return (
      <div className="flex justify-start">
        <ClarifyCard
          prompt={clarifyPrompt}
          disabled={clarifyDisabled || !onClarifyAnswer}
          timestamp={message.created_at}
          onAnswer={onClarifyAnswer}
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
        {/* 工具调用摘要 */}
        {!isUser && hasVisibleTools && (
          <div className="mb-2 space-y-2 border-b border-border/50 pb-2">
            {toolTimeline.map((item, index) => (
              <div
                key={item.key}
                className="rounded-lg bg-background/60 px-2 py-2"
              >
                <div className="flex items-center justify-between gap-3 text-xs">
                  <div className="flex min-w-0 items-center gap-1.5">
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-muted text-[10px] font-medium text-muted-foreground">
                      {index + 1}
                    </span>
                    <span className="font-mono text-muted-foreground">&#9881;</span>
                    <span className="truncate font-medium">{item.name}</span>
                  </div>
                  <span
                    className={
                      item.status === 'error' || item.status === 'failed'
                        ? 'shrink-0 text-destructive'
                        : 'shrink-0 text-muted-foreground'
                    }
                  >
                    {item.status}
                  </span>
                </div>
                {item.result && (
                  <div className="mt-2 max-h-28 overflow-y-auto whitespace-pre-wrap rounded-md bg-background/70 px-2 py-1.5 text-xs text-muted-foreground">
                    {item.result}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        {!isUser && clarifyPrompt && (
          <div className={hasVisibleTools ? 'mt-2' : ''}>
            <ClarifyCard
              prompt={clarifyPrompt}
              disabled={clarifyDisabled || !onClarifyAnswer}
              timestamp={message.created_at}
              onAnswer={onClarifyAnswer}
            />
          </div>
        )}

        {/* 消息内容 */}
        {(displayContent.trim() || isStreaming || !clarifyPrompt) && (
          <div className="whitespace-pre-wrap text-sm leading-relaxed">
            {displayContent || (isStreaming ? '' : '...')}
            {isStreaming && !displayContent && (
              <span className="inline-block h-4 w-1 animate-pulse bg-current" />
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
