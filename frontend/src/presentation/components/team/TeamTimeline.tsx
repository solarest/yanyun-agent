/**
 * 表现层 - Team 执行时间线
 *
 * 时间线渲染与 Agent 对话页完全一致：
 * - Segment 按时间顺序追加（thinking → tool_call → tool_result → text → ...）
 * - buildTimeline 将连续同类型 segment 合并渲染
 * - 以 system 消息为界分组，每组非 system 段共享一个 card
 */
import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ToolCallGroup } from '@presentation/components/chat/ToolCallGroup';
import { ThinkingBlock } from '@presentation/components/chat/ThinkingBlock';
import { MultiClarifyCard } from '@presentation/components/chat/MultiClarifyCard';

// ═══════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════

/** 时间线段 — 与 chat MessageSegment 保持一致 */
export interface TimelineSegment {
  type: 'thinking' | 'tool' | 'text' | 'system';
  content: string;
  toolCallId?: string;
  toolName?: string;
  toolStatus?: string;
  toolInput?: Record<string, unknown>;
  toolResult?: string;
}

/** ToolCallGroup 需要的 item 格式 */
interface ToolTimelineItem {
  key: string;
  name: string;
  status: string;
  result?: string;
  input?: Record<string, unknown>;
}

/** buildTimeline 渲染项 */
export interface TimelineRenderItem {
  type: 'thinking' | 'text' | 'tool_group' | 'system' | 'clarify';
  content?: string;
  tools?: ToolTimelineItem[];
  toolCallId?: string;
}

// ═══════════════════════════════════════════════════════
// Segment helpers
// ═══════════════════════════════════════════════════════

let _sid = 0;
function nextSid() {
  _sid += 1;
  return String(_sid);
}

/** 将 TimelineSegment[] 转换为可渲染的时间线项（与 chat buildTimelineFromSegments 一致） */
export function buildTimeline(segments: TimelineSegment[]): TimelineRenderItem[] {
  const items: TimelineRenderItem[] = [];
  for (const seg of segments) {
    if (seg.type === 'system') {
      items.push({ type: 'system', content: seg.content });
    } else if (seg.type === 'tool') {
      // clarify 工具：用 chat 的 MultiClarifyCard 渲染为交互框（而非普通工具卡片）
      if (seg.toolName === 'clarify' && seg.toolResult) {
        items.push({ type: 'clarify', content: seg.toolResult, toolCallId: seg.toolCallId });
      } else {
        const last = items[items.length - 1];
        const tool: ToolTimelineItem = {
          key: seg.toolCallId || nextSid(),
          name: seg.content || seg.toolName || '',
          status: seg.toolStatus || 'running',
          result: seg.toolResult,
          input: seg.toolInput,
        };
        if (last?.type === 'tool_group') {
          last.tools!.push(tool);
        } else {
          items.push({ type: 'tool_group', tools: [tool] });
        }
      }
    } else if (seg.type === 'thinking') {
      const last = items[items.length - 1];
      if (last?.type === 'thinking') {
        last.content = (last.content || '') + (seg.content || '');
      } else {
        items.push({ type: 'thinking', content: seg.content || '' });
      }
    } else {
      // text
      const last = items[items.length - 1];
      if (last?.type === 'text') {
        last.content = (last.content || '') + (seg.content || '');
      } else {
        items.push({ type: 'text', content: seg.content || '' });
      }
    }
  }
  return items;
}

export const PHASE_LABELS: Record<string, string> = {
  idle: '空闲',
  running: '执行中',
  completed: '已完成',
  failed: '失败',
};

// ═══════════════════════════════════════════════════════
// Sub-components
// ═══════════════════════════════════════════════════════

/** 系统消息 */
const SystemEntry: React.FC<{ content: string }> = ({ content }) => (
  <div className="py-1 pl-3 border-l-2 border-muted-foreground/15">
    <span className="text-xs text-muted-foreground/60 whitespace-pre-wrap leading-relaxed">{content}</span>
  </div>
);

/** 将 items 按 system 分割为卡片组，与 chat 的 message → segments 结构一致 */
function partitionItems(
  items: TimelineRenderItem[],
): Array<{ type: 'system'; content: string } | { type: 'card'; children: TimelineRenderItem[] }> {
  const result: Array<{ type: 'system'; content: string } | { type: 'card'; children: TimelineRenderItem[] }> = [];
  let buf: TimelineRenderItem[] = [];
  for (const item of items) {
    if (item.type === 'system') {
      if (buf.length > 0) {
        result.push({ type: 'card', children: buf });
        buf = [];
      }
      result.push({ type: 'system', content: item.content! });
    } else {
      buf.push(item);
    }
  }
  if (buf.length > 0) result.push({ type: 'card', children: buf });
  return result;
}

interface TeamTimelineProps {
  items: TimelineRenderItem[];
  isStreaming: boolean;
  activeClarifyId?: string | null;
  onClarifyAnswer?: (answer: string) => void;
}

/** 时间线 — 以 system 消息为界分组，每组非 system 段共享一个 card（与 chat 一致） */
export const TeamTimeline: React.FC<TeamTimelineProps> = ({
  items,
  isStreaming,
  activeClarifyId,
  onClarifyAnswer,
}) => {
  if (items.length === 0) {
    return isStreaming ? (
      <div className="rounded-2xl border border-border/50 bg-card px-4 py-3">
        <span className="inline-block h-4 w-1 animate-pulse bg-current" />
      </div>
    ) : null;
  }

  const parts = partitionItems(items);
  return (
    <>
      {parts.map((part, pi) => {
        if (part.type === 'system') {
          return <SystemEntry key={`s-${pi}`} content={part.content} />;
        }
        // card: 连续的非 system 段共享一个气泡，与 chat MessageBubble 的 segment 渲染完全一致
        return (
          <div key={`c-${pi}`} className="rounded-2xl border border-border/50 bg-card px-4 py-3">
            {part.children.map((item, idx) => {
              if (item.type === 'thinking') {
                return <ThinkingBlock key={`t-${idx}`} content={item.content!} isStreaming={isStreaming} />;
              }
              if (item.type === 'tool_group') {
                return <ToolCallGroup key={`g-${idx}`} items={item.tools!} isStreaming={isStreaming} />;
              }
              if (item.type === 'clarify') {
                // 复用 chat 的 MultiClarifyCard：仅末尾未回复的澄清框可交互，其余置为已回复
                const isActive = !!onClarifyAnswer && !!item.toolCallId && item.toolCallId === activeClarifyId;
                return (
                  <MultiClarifyCard
                    key={`cl-${item.toolCallId || idx}`}
                    content={item.content || ''}
                    submitted={!isActive}
                    disabled={!isActive}
                    onAnswer={isActive ? (answers: string[]) => onClarifyAnswer?.(answers.join('\n')) : undefined}
                  />
                );
              }
              if (item.type === 'text') {
                return (
                  <div key={`x-${idx}`} className="markdown-content text-sm leading-relaxed">
                    {item.content ? (
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{item.content}</ReactMarkdown>
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
      })}
    </>
  );
};

/** 运行状态徽章 */
export const StatusBadge: React.FC<{ status: string }> = ({ status }) => {
  const colors: Record<string, string> = {
    idle: 'bg-secondary text-muted-foreground',
    running: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
    completed: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400',
    failed: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  };
  return (
    <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${colors[status] ?? ''}`}>
      {PHASE_LABELS[status] || status}
    </span>
  );
};
