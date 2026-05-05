/**
 * 表现层 - 消息列表
 * 
 * 渲染会话消息列表，支持自动滚动和澄清卡片显示。
 */
import React, { useCallback, useEffect, useMemo, useRef } from 'react';
import type { SessionMessage } from '@domain/entities/session';
import { MessageBubble } from './MessageBubble';
import { parseAllClarifyPrompts } from './MultiClarifyCard';

interface MessageListProps {
  messages: SessionMessage[];
  isStreaming: boolean;
  onClarifyAnswer?: (answer: string) => void;
}

export const MessageList: React.FC<MessageListProps> = ({
  messages,
  isStreaming,
  onClarifyAnswer,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const shouldAutoScrollRef = useRef(true);
  const previousMessageCountRef = useRef(0);

  const handleScroll = useCallback(() => {
    const container = containerRef.current;
    if (!container) return;
    const distanceFromBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight;
    shouldAutoScrollRef.current = distanceFromBottom < 96;
  }, []);

  const activeClarifyMessageId = useMemo(() => {
    if (isStreaming || messages.length === 0) return null;
    const lastMessage = messages[messages.length - 1];
    if (lastMessage.role !== 'assistant') return null;
    
    // 从 message.content 中解析 clarify 问题（支持单个或多个）
    const allPrompts = parseAllClarifyPrompts(lastMessage.content);
    return allPrompts.length > 0 ? lastMessage.id : null;
  }, [isStreaming, messages]);

  // 自动滚动：仅当新增消息且用户在底部附近时触发
  useEffect(() => {
    if (messages.length > previousMessageCountRef.current && shouldAutoScrollRef.current) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
    previousMessageCountRef.current = messages.length;
  }, [messages.length]);

  if (messages.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <div className="text-center">
          <p className="text-lg text-muted-foreground">Start a conversation</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Send a message to begin chatting with the agent.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      onScroll={handleScroll}
      className="flex-1 overflow-y-auto px-4 py-4"
    >
      <div className="mx-auto max-w-3xl space-y-4">
        {messages.map((msg) => (
          <MessageBubble
            key={msg.id}
            message={msg}
            clarifyDisabled={msg.id !== activeClarifyMessageId}
            onClarifyAnswer={
              msg.id === activeClarifyMessageId ? onClarifyAnswer : undefined
            }
          />
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
};
