/**
 * 表现层 - 消息气泡
 */
import React from 'react';
import type { SessionMessage } from '@domain/entities/session';

interface MessageBubbleProps {
  message: SessionMessage;
}

export const MessageBubble: React.FC<MessageBubbleProps> = ({ message }) => {
  const isUser = message.role === 'user';
  const isError = message.status === 'error';
  const isStreaming = message.status === 'streaming';

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
        {/* 消息内容 */}
        <div className="whitespace-pre-wrap text-sm leading-relaxed">
          {message.content || (isStreaming ? '' : '...')}
          {isStreaming && !message.content && (
            <span className="inline-block h-4 w-1 animate-pulse bg-current" />
          )}
        </div>

        {/* 工具调用摘要 */}
        {!isUser && message.tool_calls.length > 0 && (
          <div className="mt-2 space-y-1 border-t border-border/50 pt-2">
            {message.tool_calls.map((tc, i) => (
              <div
                key={tc.id || i}
                className="flex items-center gap-1.5 text-xs text-muted-foreground"
              >
                <span className="font-mono">&#9881;</span>
                <span>{tc.name}</span>
              </div>
            ))}
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
