/**
 * 表现层 - 消息时间线渲染（segments → 视觉时间线）
 *
 * 从 MessageBubble 抽出的纯展示部分：
 * 按 segments 实际事件顺序渲染 thinking / tool_group / text，
 * 连续同类型片段由 buildTimelineFromSegments 合并。
 * clarify 提交状态由父组件控制（同一消息的 clarify 卡片共享 submitted 状态）。
 */
import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { MessageSegment } from '@domain/entities/session';
import { ThinkingBlock } from './ThinkingBlock';
import { ToolCallGroup } from './ToolCallGroup';
import { CommandConfirmCard } from './CommandConfirmCard';
import { ClarifyCard } from './ClarifyCard';
import { MultiClarifyCard, parseAllClarifyPrompts } from './MultiClarifyCard';
import { approvalApi } from '@infrastructure/api/approvals';
import type { ToolTimelineItem } from './ToolTimeline';

// ── 时间线片段工具函数 ──────────────────────────────────────

/** 将 segments 转换为可渲染的时间线项，连续 tool 片段自动合并为 ToolCallGroup */
interface TimelineRenderItem {
  type: 'thinking' | 'text' | 'tool_group';
  /** thinking/text: 文本内容 */
  content?: string;
  /** tool_group: 工具列表 */
  tools?: ToolTimelineItem[];
}

export function buildTimelineFromSegments(
  segments: MessageSegment[],
): TimelineRenderItem[] {
  const items: TimelineRenderItem[] = [];

  for (const seg of segments) {
    if (seg.type === 'tool') {
      const lastItem = items[items.length - 1];
      const toolItem: ToolTimelineItem = {
        key: seg.toolCallId || seg.content || '',
        name: seg.content || '',
        status: seg.toolStatus || 'running',
        result: seg.toolResult,
        input: seg.toolInput,
        riskReason: seg.riskReason,
      };
      if (lastItem && lastItem.type === 'tool_group') {
        // 追加到上一个工具组
        lastItem.tools!.push(toolItem);
      } else {
        // 新建工具组
        items.push({ type: 'tool_group', tools: [toolItem] });
      }
    } else if (seg.type === 'thinking') {
      const lastItem = items[items.length - 1];
      if (lastItem?.type === 'thinking') {
        // 合并连续 thinking 片段
        lastItem.content = (lastItem.content || '') + (seg.content || '');
      } else {
        items.push({ type: 'thinking', content: seg.content || '' });
      }
    } else {
      // text segment
      const lastItem = items[items.length - 1];
      if (lastItem?.type === 'text') {
        // 合并连续 text 片段
        lastItem.content = (lastItem.content || '') + (seg.content || '');
      } else {
        items.push({ type: 'text', content: seg.content || '' });
      }
    }
  }

  return items;
}

/** 将 text 内容拆分为 clarify 问题文本之外的其余内容（prompts 需已解析） */
function contentWithoutClarifyQuestions(
  textContent: string,
  allClarify: ReturnType<typeof parseAllClarifyPrompts>,
): string {
  if (allClarify.length === 0) return textContent;
  const questionsOnly = allClarify.map((c) => c.question).join('\n');
  const withoutQuestions = textContent.replace(questionsOnly, '').trim();
  const optionsOnly = allClarify.map((c) => c.options?.join('\n') || '').join('\n');
  return withoutQuestions === optionsOnly ? '' : withoutQuestions;
}

interface MessageTimelineProps {
  segments: MessageSegment[];
  isStreaming: boolean;
  isThinking: boolean;
  createdAt: string;
  taskId: string | null;
  clarifyDisabled: boolean;
  clarifySubmitted: boolean;
  onClarifyAnswer?: (answer: string) => void;
}

export const MessageTimeline: React.FC<MessageTimelineProps> = ({
  segments,
  isStreaming,
  isThinking,
  createdAt,
  taskId,
  clarifyDisabled,
  clarifySubmitted,
  onClarifyAnswer,
}) => {
  // 危险命令确认提交记录（仅时间线内的确认卡片使用）
  const [confirmSubmitted, setConfirmSubmitted] = useState<Set<string>>(
    () => new Set(),
  );

  const timeline = buildTimelineFromSegments(segments);

  return (
    <div className="space-y-1.5">
      {timeline.map((item, idx) => {
        if (item.type === 'thinking') {
          return (
            <ThinkingBlock
              key={`thinking-${idx}`}
              content={item.content || ''}
              isStreaming={Boolean(isThinking)}
            />
          );
        }
        if (item.type === 'tool_group') {
          // 单次遍历分区：待确认 / 其余
          const awaiting: ToolTimelineItem[] = [];
          const rest: ToolTimelineItem[] = [];
          for (const t of item.tools!) {
            if (t.status === 'awaiting_confirmation') {
              awaiting.push(t);
            } else {
              rest.push(t);
            }
          }
          return (
            <React.Fragment key={`tools-${idx}`}>
              {rest.length > 0 && (
                <ToolCallGroup items={rest} isStreaming={isStreaming} />
              )}
              {awaiting.map((t) => (
                <CommandConfirmCard
                  key={`confirm-${t.key}`}
                  command={String(t.input?.command ?? '')}
                  riskReason={t.riskReason}
                  submitted={confirmSubmitted.has(t.key)}
                  timestamp={createdAt}
                  onDecision={(decision) => {
                    approvalApi.postApproval(taskId || '', t.key, decision);
                    setConfirmSubmitted((prev) => new Set(prev).add(t.key));
                  }}
                />
              ))}
            </React.Fragment>
          );
        }
        if (item.type === 'text') {
          const textContent = item.content || '';
          const allClarify = parseAllClarifyPrompts(textContent);
          if (
            allClarify.length > 0 &&
            contentWithoutClarifyQuestions(textContent, allClarify).length === 0
          ) {
            if (allClarify.length === 1) {
              return (
                <ClarifyCard
                  key={`text-${idx}`}
                  prompt={allClarify[0]}
                  disabled={clarifyDisabled || !onClarifyAnswer}
                  submitted={clarifySubmitted}
                  timestamp={createdAt}
                  onAnswer={(answer: string) => onClarifyAnswer?.(answer)}
                />
              );
            }
            return (
              <MultiClarifyCard
                key={`text-${idx}`}
                content={textContent}
                disabled={clarifyDisabled || !onClarifyAnswer}
                submitted={clarifySubmitted}
                timestamp={createdAt}
                onAnswer={(answers: string[]) => onClarifyAnswer?.(answers.join('\n'))}
              />
            );
          }
          return (
            <div key={`text-${idx}`} className="markdown-content text-sm leading-relaxed">
              {textContent ? (
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {textContent}
                </ReactMarkdown>
              ) : (
                isStreaming && <span className="inline-block h-4 w-1 animate-pulse bg-current" />
              )}
            </div>
          );
        }
        return null;
      })}
    </div>
  );
};
