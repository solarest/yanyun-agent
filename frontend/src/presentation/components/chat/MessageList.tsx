/**
 * 表现层 - 消息列表
 *
 * 时间线布局渲染会话消息，支持自动滚动和澄清卡片显示。
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

interface RenderMessageItem {
  message: SessionMessage;
  embeddedSubAgents: SessionMessage[];
}

const isSubAgentMessage = (message: SessionMessage): boolean =>
  Boolean(message.meta?.isSubAgent);

export const MessageList: React.FC<MessageListProps> = ({
  messages,
  isStreaming,
  onClarifyAnswer,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const shouldAutoScrollRef = useRef(true);
  const previousMessageCountRef = useRef(0);

  const renderItems = useMemo<RenderMessageItem[]>(() => {
    const items: RenderMessageItem[] = [];

    messages.forEach((message) => {
      if (!isSubAgentMessage(message)) {
        items.push({ message, embeddedSubAgents: [] });
        return;
      }

      const parentItem = [...items]
        .reverse()
        .find((item) => item.message.role === 'assistant');

      if (parentItem) {
        parentItem.embeddedSubAgents.push(message);
      } else {
        items.push({ message, embeddedSubAgents: [] });
      }
    });

    return items;
  }, [messages]);

  const handleScroll = useCallback(() => {
    const container = containerRef.current;
    if (!container) return;
    const distanceFromBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight;
    shouldAutoScrollRef.current = distanceFromBottom < 96;
  }, []);

  const activeClarifyMessageId = useMemo(() => {
    if (isStreaming || renderItems.length === 0) return null;
    const lastMessage = renderItems[renderItems.length - 1].message;
    if (lastMessage.role !== 'assistant') return null;

    const allPrompts = parseAllClarifyPrompts(lastMessage.content);
    return allPrompts.length > 0 ? lastMessage.id : null;
  }, [isStreaming, renderItems]);

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
          <p className="text-lg text-muted-foreground">开始对话</p>
          <p className="mt-1 text-sm text-muted-foreground">
            发送消息开始与 Agent 对话
          </p>
        </div>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      onScroll={handleScroll}
      className="flex-1 overflow-y-auto px-4 py-6"
    >
      <div className="mx-auto max-w-3xl relative">
        {/* 垂直时间线 */}
        <div className="absolute left-3 top-2 bottom-2 w-px bg-border/60" />

        {renderItems.map(({ message: msg, embeddedSubAgents }) => (
          <MessageBubble
            key={msg.id}
            message={msg}
            embeddedSubAgents={embeddedSubAgents}
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
