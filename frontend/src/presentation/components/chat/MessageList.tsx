/**
 * 表现层 - 消息列表
 *
 * 时间线布局渲染会话消息，支持自动滚动和澄清卡片显示。
 *
 * 渲染优化：
 * - 子代理消息折叠进最近的 assistant 消息（embeddedSubAgents 仅非空时赋值，
 *   配合 MessageBubble 的 React.memo 保证历史消息浅比较稳定）
 * - 自动滚动：新消息用 smooth，流式内容增长用 auto（每 chunk 代价最小化）；
 *   用户上滑离开底部后暂停跟随
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
  embeddedSubAgents?: SessionMessage[];
}

const isSubAgentMessage = (message: SessionMessage): boolean =>
  Boolean(message.meta?.isSubAgent);

/** 距底部小于该距离视为"在底部"，自动跟随滚动 */
const AUTO_SCROLL_THRESHOLD_PX = 96;

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
    // 最近的 assistant 消息下标（子代理消息按其时间顺序归属到最近的父消息）
    let lastAssistantIndex = -1;

    messages.forEach((message) => {
      if (!isSubAgentMessage(message)) {
        if (message.role === 'assistant') {
          lastAssistantIndex = items.length;
        }
        items.push({ message });
        return;
      }

      if (lastAssistantIndex >= 0) {
        const parentItem = items[lastAssistantIndex];
        parentItem.embeddedSubAgents = [
          ...(parentItem.embeddedSubAgents || []),
          message,
        ];
      } else {
        items.push({ message });
      }
    });

    return items;
  }, [messages]);

  const handleScroll = useCallback(() => {
    const container = containerRef.current;
    if (!container) return;
    const distanceFromBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight;
    shouldAutoScrollRef.current = distanceFromBottom < AUTO_SCROLL_THRESHOLD_PX;
  }, []);

  const activeClarifyMessageId = useMemo(() => {
    if (isStreaming || renderItems.length === 0) return null;
    const lastMessage = renderItems[renderItems.length - 1].message;
    if (lastMessage.role !== 'assistant') return null;

    const allPrompts = parseAllClarifyPrompts(lastMessage.content);
    return allPrompts.length > 0 ? lastMessage.id : null;
  }, [isStreaming, renderItems]);

  // 自动滚动：新消息 smooth 滚动；流式内容增长用 auto（每 chunk 检查一次，开销小）
  useEffect(() => {
    if (!shouldAutoScrollRef.current) return;
    const isNewMessage = messages.length > previousMessageCountRef.current;
    previousMessageCountRef.current = messages.length;
    bottomRef.current?.scrollIntoView({
      behavior: isNewMessage ? 'smooth' : 'auto',
      block: 'end',
    });
  }, [messages]);

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
      <div className="mx-auto max-w-3xl">
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
