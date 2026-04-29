/**
 * 表现层 - 消息列表
 */
import React, { useEffect, useRef } from 'react';
import type { SessionMessage } from '@domain/entities/session';
import { MessageBubble } from './MessageBubble';

interface MessageListProps {
  messages: SessionMessage[];
  isStreaming: boolean;
}

export const MessageList: React.FC<MessageListProps> = ({
  messages,
  isStreaming,
}) => {
  const bottomRef = useRef<HTMLDivElement>(null);

  // 自动滚动到底部
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isStreaming]);

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
    <div className="flex-1 overflow-y-auto px-4 py-4">
      <div className="mx-auto max-w-3xl space-y-4">
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
};
