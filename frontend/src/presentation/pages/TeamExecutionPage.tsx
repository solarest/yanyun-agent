/**
 * 表现层 - Team 执行页
 *
 * 时间线渲染与 Agent 对话页完全一致：
 * - Segment 按时间顺序追加（thinking → tool_call → tool_result → text → ...）
 * - buildTimeline 将连续同类型 segment 合并渲染
 */
import React, { useEffect, useState, useCallback, useMemo, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useTeamManagement } from '@application/services/useTeamManagement';
import { AgentEventStream } from '@infrastructure/api/eventStream';
import { ToolCallGroup } from '@presentation/components/chat/ToolCallGroup';
import { ThinkingBlock } from '@presentation/components/chat/ThinkingBlock';
import { MultiClarifyCard } from '@presentation/components/chat/MultiClarifyCard';
import type { TeamMember } from '@domain/entities/team';

// ═══════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════

type RunState = 'idle' | 'running' | 'completed' | 'failed';

/** 时间线段 — 与 chat MessageSegment 保持一致 */
interface TimelineSegment {
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
interface TimelineRenderItem {
  type: 'thinking' | 'text' | 'tool_group' | 'system' | 'clarify';
  content?: string;
  tools?: ToolTimelineItem[];
  toolCallId?: string;
}

interface MemberRunState {
  agentId: string;
  agentName: string;
  status: 'idle' | 'busy' | 'done';
  taskId?: string;
  taskDescription?: string;
  result?: string;
  segments: TimelineSegment[];
}

// ═══════════════════════════════════════════════════════
// Segment helpers
// ═══════════════════════════════════════════════════════

let _sid = 0;
function nextSid() { _sid += 1; return String(_sid); }

/** 将 TimelineSegment[] 转换为可渲染的时间线项（与 chat buildTimelineFromSegments 一致） */
function buildTimeline(segments: TimelineSegment[]): TimelineRenderItem[] {
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

const PHASE_LABELS: Record<string, string> = {
  idle: '空闲', running: '执行中', completed: '已完成', failed: '失败',
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
function partitionItems(items: TimelineRenderItem[]): Array<{ type: 'system'; content: string } | { type: 'card'; children: TimelineRenderItem[] }> {
  const result: Array<{ type: 'system'; content: string } | { type: 'card'; children: TimelineRenderItem[] }> = [];
  let buf: TimelineRenderItem[] = [];
  for (const item of items) {
    if (item.type === 'system') {
      if (buf.length > 0) { result.push({ type: 'card', children: buf }); buf = []; }
      result.push({ type: 'system', content: item.content! });
    } else {
      buf.push(item);
    }
  }
  if (buf.length > 0) result.push({ type: 'card', children: buf });
  return result;
}

/** 时间线 — 以 system 消息为界分组，每组非 system 段共享一个 card（与 chat 一致） */
const TimelineBubble: React.FC<{
  items: TimelineRenderItem[];
  isStreaming: boolean;
  activeClarifyId?: string | null;
  onClarifyAnswer?: (answer: string) => void;
}> = ({ items, isStreaming, activeClarifyId, onClarifyAnswer }) => {
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

const StatusBadge: React.FC<{ status: string }> = ({ status }) => {
  const colors: Record<string, string> = {
    idle: 'bg-secondary text-muted-foreground',
    running: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
    completed: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400',
    failed: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  };
  return <span className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${colors[status] ?? ''}`}>{PHASE_LABELS[status] || status}</span>;
};

// ═══════════════════════════════════════════════════════
// Main Component
// ═══════════════════════════════════════════════════════

export const TeamExecutionPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const { currentTeam, fetchTeam, executeTeam, isLoading: teamLoading, error: teamError } = useTeamManagement();

  const [goal, setGoal] = useState('');
  const [runState, setRunState] = useState<RunState>('idle');
  const [executionId, setExecutionId] = useState<string | null>(null);
  const [workspace, setWorkspace] = useState('/tmp/team-workspace');
  const [activeTab, setActiveTab] = useState<string>('leader');
  const [leaderSegments, setLeaderSegments] = useState<TimelineSegment[]>([]);
  const [memberStates, setMemberStates] = useState<Map<string, MemberRunState>>(new Map());
  const [finalResult, setFinalResult] = useState('');
  const [finalResultExpanded, setFinalResultExpanded] = useState(false);
  const [goalInputFocused, setGoalInputFocused] = useState(false);
  const [isStreamingLeader, setIsStreamingLeader] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [workspaceFiles, setWorkspaceFiles] = useState<Array<{ name: string; path: string; is_dir: boolean; size: number; modified_at: number }>>([]);
  const [followUpInput, setFollowUpInput] = useState('');
  const [isFollowUpRunning, setIsFollowUpRunning] = useState(false);

  const streamRef = useRef<AgentEventStream | null>(null);
  const memberStreamsRef = useRef<Map<string, AgentEventStream>>(new Map());
  const logsEndRef = useRef<HTMLDivElement>(null);
  const followUpRef = useRef('');
  const runningRef = useRef(false);
  // 当前 leader 会话 ID：首次执行从响应中获取，追问时回传以保持澄清链路上下文连续
  const leaderSessionIdRef = useRef<string | null>(null);
  // 当前活跃的澄清 toolCallId：仅末尾未回复的澄清框可交互，回复/新执行时清空
  const [activeClarifyId, setActiveClarifyId] = useState<string | null>(null);
  const activeClarifyIdRef = useRef<string | null>(null);

  useEffect(() => { if (id) fetchTeam(id); }, [id, fetchTeam]);
  useEffect(() => {
    return () => { streamRef.current?.disconnect(); memberStreamsRef.current.forEach((s) => s.disconnect()); };
  }, []);
  useEffect(() => { logsEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [leaderSegments]);

  // ── Workspace file polling ──
  const fetchWorkspaceFiles = useCallback(async () => {
    if (!id) return;
    try {
      const res = await fetch(`/api/teams/${id}/workspace-files?path=${encodeURIComponent(workspace)}`);
      const data = await res.json();
      setWorkspaceFiles(data.files || []);
    } catch { /* ignore */ }
  }, [id, workspace]);

  useEffect(() => {
    if (runState !== 'idle' && sidebarOpen) {
      fetchWorkspaceFiles();
      const interval = setInterval(fetchWorkspaceFiles, 3000);
      return () => clearInterval(interval);
    }
  }, [runState, sidebarOpen, fetchWorkspaceFiles]);

  const members: TeamMember[] = currentTeam?.members ?? [];
  const leader = members.find((m) => m.role === 'leader');
  const regularMembers = members.filter((m) => m.role === 'member');
  // ref 镜像：SSE handler（含恢复重连）需读取最新的成员列表，避免闭包 stale
  const regularMembersRef = useRef(regularMembers);
  regularMembersRef.current = regularMembers;

  const allTabs = [
    { key: 'leader', label: leader?.agent_name || 'Leader', agentId: leader?.agent_id || '', role: 'leader' as const },
    ...regularMembers.map((m) => ({ key: m.agent_id, label: m.agent_name || m.agent_id, agentId: m.agent_id, role: 'member' as const })),
  ];

  const currentSegments = activeTab === 'leader'
    ? leaderSegments
    : memberStates.get(activeTab)?.segments ?? [];

  // ── Segment mutation helpers ──
  const pushLeaderSegment = useCallback((seg: TimelineSegment) => {
    setLeaderSegments((prev) => [...prev, seg]);
  }, []);

  const updateLastLeaderSegment = useCallback((updater: (seg: TimelineSegment) => TimelineSegment) => {
    setLeaderSegments((prev) => {
      if (prev.length === 0) return prev;
      return [...prev.slice(0, -1), updater(prev[prev.length - 1])];
    });
  }, []);

  const appendLeaderText = useCallback((chunk: string) => {
    setLeaderSegments((prev) => {
      const last = prev[prev.length - 1];
      if (last?.type === 'text') {
        return [...prev.slice(0, -1), { ...last, content: last.content + chunk }];
      }
      return [...prev, { type: 'text', content: chunk }];
    });
  }, []);

  const appendLeaderThinking = useCallback((chunk: string) => {
    setLeaderSegments((prev) => {
      const last = prev[prev.length - 1];
      if (last?.type === 'thinking') {
        return [...prev.slice(0, -1), { ...last, content: last.content + chunk }];
      }
      return [...prev, { type: 'thinking' as const, content: chunk }];
    });
  }, []);

  const addLeaderSystem = useCallback((msg: string) => {
    setLeaderSegments((prev) => [...prev, { type: 'system', content: msg }]);
  }, []);

  // ── Member segment helpers ──
  const pushMemberSegment = useCallback((agentId: string, seg: TimelineSegment) => {
    setMemberStates((prev) => {
      const next = new Map(prev);
      const existing = next.get(agentId) || { agentId, agentName: '', status: 'idle' as const, segments: [] };
      next.set(agentId, { ...existing, segments: [...existing.segments, seg] });
      return next;
    });
  }, []);

  const appendMemberText = useCallback((agentId: string, chunk: string) => {
    setMemberStates((prev) => {
      const next = new Map(prev);
      const existing = next.get(agentId);
      if (!existing) return prev;
      const segs = existing.segments;
      const last = segs[segs.length - 1];
      if (last?.type === 'text') {
        next.set(agentId, { ...existing, segments: [...segs.slice(0, -1), { ...last, content: last.content + chunk }] });
      } else {
        next.set(agentId, { ...existing, segments: [...segs, { type: 'text', content: chunk }] });
      }
      return next;
    });
  }, []);

  const appendMemberThinking = useCallback((agentId: string, chunk: string) => {
    setMemberStates((prev) => {
      const next = new Map(prev);
      const existing = next.get(agentId);
      if (!existing) return prev;
      const segs = existing.segments;
      const last = segs[segs.length - 1];
      if (last?.type === 'thinking') {
        next.set(agentId, { ...existing, segments: [...segs.slice(0, -1), { ...last, content: last.content + chunk }] });
      } else {
        next.set(agentId, { ...existing, segments: [...segs, { type: 'thinking' as const, content: chunk }] });
      }
      return next;
    });
  }, []);

  const addMemberSystem = useCallback((agentId: string, msg: string) => {
    setMemberStates((prev) => {
      const next = new Map(prev);
      const existing = next.get(agentId) || { agentId, agentName: '', status: 'idle' as const, segments: [] };
      next.set(agentId, { ...existing, segments: [...existing.segments, { type: 'system', content: msg }] });
      return next;
    });
  }, []);

  // ── Stream binding ──
  const bindMemberStream = useCallback((agentId: string, taskId: string, agentName: string) => {
    memberStreamsRef.current.get(agentId)?.disconnect();
    const stream = new AgentEventStream('', taskId);
    memberStreamsRef.current.set(agentId, stream);

    stream.on('tool:call', (payload: any) => {
      pushMemberSegment(agentId, {
        type: 'tool', content: payload.toolName || '',
        toolCallId: payload.toolCallId, toolName: payload.toolName,
        toolStatus: 'running', toolInput: payload.input || {},
      });
    });
    stream.on('tool:result', (payload: any) => {
      setMemberStates((prev) => {
        const next = new Map(prev);
        const existing = next.get(agentId);
        if (!existing) return prev;
        const segs = [...existing.segments];
        for (let i = segs.length - 1; i >= 0; i--) {
          if (segs[i].type === 'tool' && segs[i].toolStatus === 'running' && (!payload.toolCallId || segs[i].toolCallId === payload.toolCallId)) {
            segs[i] = { ...segs[i], toolStatus: payload.status === 'success' ? 'success' : 'error', toolResult: (payload.output || '').slice(0, 3000) };
            break;
          }
        }
        next.set(agentId, { ...existing, segments: segs });
        return next;
      });
    });
    stream.on('thinking:chunk', (payload: any) => {
      if (payload.text) appendMemberThinking(agentId, payload.text);
    });
    stream.on('llm:chunk', (payload: any) => {
      if (payload.text) appendMemberText(agentId, payload.text);
    });
    stream.on('task:completed', () => {
      addMemberSystem(agentId, '✅ 任务执行完成');
      setMemberStates((prev) => { const next = new Map(prev); const e = next.get(agentId); if (e) next.set(agentId, { ...e, status: 'done' }); return next; });
    });
    stream.on('task:failed', (payload: any) => {
      addMemberSystem(agentId, `❌ 任务失败: ${payload.error || 'Unknown'}`);
      setMemberStates((prev) => { const next = new Map(prev); const e = next.get(agentId); if (e) next.set(agentId, { ...e, status: 'done' }); return next; });
    });
    stream.connect();
  }, [pushMemberSegment, appendMemberThinking, appendMemberText, addMemberSystem]);

  // ── localStorage 持久化活跃执行（复用 chat 的刷新恢复模式）──
  const TEAM_EXEC_KEY = 'activeTeamExecution';

  const saveActiveExecution = useCallback((executionId: string, sessionId: string) => {
    if (!id) return;
    try {
      localStorage.setItem(TEAM_EXEC_KEY, JSON.stringify({
        teamId: id, executionId, sessionId, timestamp: Date.now(),
      }));
    } catch { /* ignore */ }
  }, [id]);

  const clearActiveExecution = useCallback(() => {
    try { localStorage.removeItem(TEAM_EXEC_KEY); } catch { /* ignore */ }
  }, []);

  /**
   * 绑定 leader SSE 事件处理器。handleExecute / handleFollowUp / 刷新恢复共用同一套
   * 事件处理 → 运行时与刷新后恢复的时序渲染完全一致（后端 SSE 在全新连接时重放全部事件）。
   */
  const bindLeaderStream = useCallback((ls: AgentEventStream, ctx: { execId: string; followUpGoal: string | null }) => {
    ls.on('tool:call', (p: any) => pushLeaderSegment({ type: 'tool', content: p.toolName || '', toolCallId: p.toolCallId, toolName: p.toolName, toolStatus: 'running', toolInput: p.input || {} }));
    ls.on('tool:result', (p: any) => {
      setLeaderSegments((prev) => {
        const segs = [...prev];
        for (let i = segs.length - 1; i >= 0; i--) {
          if (segs[i].type === 'tool' && segs[i].toolStatus === 'running' && (!p.toolCallId || segs[i].toolCallId === p.toolCallId)) {
            segs[i] = { ...segs[i], toolStatus: p.status === 'success' ? 'success' : 'error', toolResult: (p.output || '').slice(0, 3000) };
            break;
          }
        }
        return segs;
      });
      // clarify 工具：标记为活跃澄清框，等待用户在框内回复（而非作为"最终结果"）
      if (p.toolName === 'clarify' && p.status !== 'error') {
        activeClarifyIdRef.current = p.toolCallId || null;
        setActiveClarifyId(p.toolCallId || null);
      }
    });
    ls.on('thinking:chunk', (p: any) => { if (p.text) appendLeaderThinking(p.text); });
    ls.on('llm:chunk', (p: any) => { if (p.text) appendLeaderText(p.text); });

    ls.on('team:task:assigned', (p: any) => {
      const mName = regularMembersRef.current.find((m) => m.agent_id === p.agent_id)?.agent_name || p.agent_id;
      addLeaderSystem(`📤 分配任务给 ${mName}:\n${p.description || ''}`);
      setMemberStates((prev) => {
        const next = new Map(prev);
        next.set(p.agent_id, { agentId: p.agent_id, agentName: mName, status: 'busy', taskId: p.task_id, taskDescription: p.description, segments: [{ type: 'system', content: `📥 收到任务:\n${p.description || ''}` }] });
        return next;
      });
      if (p.task_id) bindMemberStream(p.agent_id, p.task_id, mName);
    });
    ls.on('team:task:reported', (p: any) => {
      const mName = regularMembersRef.current.find((m) => m.agent_id === p.agent_id)?.agent_name || p.agent_id;
      addLeaderSystem(`${p.status === 'completed' ? '✅' : '❌'} ${mName} 完成`);
      setMemberStates((prev) => { const next = new Map(prev); const e = next.get(p.agent_id); if (e) next.set(p.agent_id, { ...e, status: 'done', result: p.result }); return next; });
    });
    ls.on('team:task:updated', (p: any) => { addLeaderSystem(`📋 任务列表更新 — ${p.task_count} 项`); });
    ls.on('task:completed', () => { addLeaderSystem('✅ Leader 执行完成'); });

    ls.on('team:execution:completed', (p: any) => {
      runningRef.current = false; setIsStreamingLeader(false); setIsFollowUpRunning(false);
      if (activeClarifyIdRef.current) {
        // 澄清链路：不作为"最终结果"展示，保留澄清框与 localStorage 以便刷新后恢复
        addLeaderSystem('💬 需要补充信息，请在上方澄清框中回复');
        setRunState('completed');
      } else {
        addLeaderSystem(ctx.followUpGoal ? '🎉 追问执行完成!' : '🎉 团队执行完成!');
        setFinalResult(p.result || ''); setFinalResultExpanded(true); setRunState('completed');
        setSidebarOpen(true);
        clearActiveExecution(); // 真正完成 → 清除恢复态
      }
    });
    ls.on('team:execution:failed', (p: any) => {
      runningRef.current = false; setIsStreamingLeader(false); setIsFollowUpRunning(false);
      addLeaderSystem(`❌ 执行失败: ${p.error}`); setRunState('failed');
      clearActiveExecution();
    });
  }, [pushLeaderSegment, appendLeaderThinking, appendLeaderText, addLeaderSystem, bindMemberStream, clearActiveExecution]);

  // ── 刷新恢复：复用 chat 的 localStorage + SSE replay 模式 ──
  // 后端 SSE 在全新连接时重放该 task 的全部事件，故重连后用同一套 handler 重建 timeline，
  // 与运行时渲染完全一致；澄清等待中（未 clearActiveExecution）也会恢复澄清框。
  const restoredRef = useRef(false);
  useEffect(() => {
    if (!id) return;
    let entry: { teamId?: string; executionId?: string; sessionId?: string; timestamp?: number } | null = null;
    try {
      const raw = localStorage.getItem(TEAM_EXEC_KEY);
      if (raw) entry = JSON.parse(raw);
    } catch { /* ignore */ }
    if (!entry || entry.teamId !== id) return;
    // 超过 30min 视为陈旧，不恢复
    if (Date.now() - (entry.timestamp || 0) > 30 * 60 * 1000) { clearActiveExecution(); return; }
    // 首次恢复：设置运行状态与系统提示（StrictMode remount 时不重复设置，避免重复消息）
    if (!restoredRef.current) {
      restoredRef.current = true;
      setRunState('running'); setIsStreamingLeader(true);
      setExecutionId(entry.executionId!);
      leaderSessionIdRef.current = entry.sessionId || entry.executionId!;
      addLeaderSystem('🔄 恢复上次执行...');
    }
    // 每次挂载都（重）连 SSE 流：StrictMode 卸载会断开流，remount 需重连；
    // 后端在全新连接时重放该 task 全部事件，故用同一套 handler 重建 timeline（与运行时一致）。
    streamRef.current?.disconnect();
    const ls = new AgentEventStream('', entry.executionId!);
    streamRef.current = ls;
    ls.enableReplayMode();
    bindLeaderStream(ls, { execId: entry.executionId!, followUpGoal: null });
    ls.connect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // ── Execute ──
  const handleExecute = async () => {
    if (!goal.trim() || !id) return;
    setRunState('running'); setIsStreamingLeader(true);
    setLeaderSegments([]); setMemberStates(new Map());
    setFinalResult(''); runningRef.current = false;
    activeClarifyIdRef.current = null; setActiveClarifyId(null);

    const leaderName = leader?.agent_name || 'Leader';
    setLeaderSegments([{ type: 'system', content: `开始执行: ${goal}` }]);

    const result = await executeTeam(id, goal.trim());
    if (!result) { setRunState('failed'); setIsStreamingLeader(false); addLeaderSystem('❌ 执行启动失败'); return; }

    const execId = result.execution_id;
    setExecutionId(execId);
    leaderSessionIdRef.current = result.session_id || execId;
    if (result.workspace) setWorkspace(result.workspace);
    addLeaderSystem(`执行 ID: ${execId}`);

    saveActiveExecution(execId, result.session_id || execId);
    streamRef.current?.disconnect();
    const ls = new AgentEventStream('', execId);
    streamRef.current = ls;
    bindLeaderStream(ls, { execId, followUpGoal: null });
    ls.connect();
  };

  // ── Follow-up ──
  const handleFollowUp = useCallback(async (answer?: string) => {
    const q = (answer ?? followUpRef.current).trim();
    if (!q || !id || runningRef.current) return;
    runningRef.current = true; setFollowUpInput(''); followUpRef.current = '';
    activeClarifyIdRef.current = null; setActiveClarifyId(null);
    setIsFollowUpRunning(true); setRunState('running'); setIsStreamingLeader(true);
    addLeaderSystem(`💬 追问: ${q}`);

    const result = await executeTeam(id, q, undefined, leaderSessionIdRef.current || undefined);
    if (!result) { runningRef.current = false; setIsFollowUpRunning(false); setRunState('failed'); addLeaderSystem('❌ 追问执行失败'); return; }

    const execId = result.execution_id; setExecutionId(execId); if (result.workspace) setWorkspace(result.workspace);
    saveActiveExecution(execId, result.session_id || leaderSessionIdRef.current || execId);
    streamRef.current?.disconnect();
    const ls = new AgentEventStream('', execId);
    streamRef.current = ls;
    bindLeaderStream(ls, { execId, followUpGoal: q });
    ls.connect();
  }, [id, executeTeam, addLeaderSystem, saveActiveExecution, bindLeaderStream]);

  // 澄清框回复：复用追问链路（带 session_id），清空活跃澄清标记使该框转为已回复态
  const handleClarifyAnswer = useCallback((answer: string) => {
    activeClarifyIdRef.current = null;
    setActiveClarifyId(null);
    handleFollowUp(answer);
  }, [handleFollowUp]);

  // ── Render ──
  const timelineItems = useMemo(() => buildTimeline(currentSegments), [currentSegments]);
  const showStreaming = activeTab === 'leader' ? isStreamingLeader : false;

  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center justify-between border-b bg-card px-4 py-3">
        <div className="flex items-center gap-3">
          <Link to={`/teams/${id}`} className="text-sm text-muted-foreground hover:text-foreground">&larr; 返回</Link>
          <div className="h-5 w-px bg-border" />
          <h2 className="text-sm font-semibold">{currentTeam?.name ?? '加载中...'}</h2>
          <StatusBadge status={runState} />
          {executionId && <span className="text-xs text-muted-foreground/50 font-mono">{executionId}</span>}
        </div>
        <div className="flex items-center gap-3">
          {runState === 'running' && <span className="flex items-center gap-1.5 text-xs text-muted-foreground"><span className="h-2 w-2 animate-pulse rounded-full bg-primary" />执行中...</span>}
        </div>
      </header>

      {runState === 'idle' && (
        <div className="flex-1 flex flex-col items-center justify-center p-4">
          <div className="w-full max-w-2xl">
            <h2 className="mb-6 text-center text-xl font-semibold">团队目标</h2>
            <div className={`rounded-2xl border bg-card transition-colors ${goalInputFocused ? 'border-primary/30 shadow-sm' : 'border-border'}`}>
              <textarea className="w-full resize-none bg-transparent px-4 py-3 text-sm placeholder:text-muted-foreground/50 focus:outline-none" rows={4} placeholder="描述你的团队目标..." value={goal} onFocus={() => setGoalInputFocused(true)} onBlur={() => setGoalInputFocused(false)} onChange={(e) => setGoal(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); handleExecute(); }}} />
              <div className="flex items-center justify-between border-t border-border/50 px-3 py-2">
                <span className="text-[10px] text-muted-foreground/40">⌘ + Enter 开始执行</span>
                <button type="button" className="btn btn-primary text-sm" disabled={!goal.trim() || teamLoading} onClick={handleExecute}>{teamLoading ? '加载中...' : '开始执行'}</button>
              </div>
            </div>
            {teamError && <div className="mt-3 rounded-lg border border-destructive/20 bg-destructive/5 p-3 text-sm text-destructive">{teamError}</div>}
          </div>
        </div>
      )}

      {runState !== 'idle' && (
        <>
          <div className="flex border-b bg-card/50 px-2">
            {allTabs.map((tab) => {
              const isActive = activeTab === tab.key;
              const memberState = tab.key !== 'leader' ? memberStates.get(tab.key) : null;
              const dotColor = tab.role === 'leader' ? (runState === 'completed' ? 'bg-emerald-400' : runState === 'running' ? 'bg-primary animate-pulse' : 'bg-muted-foreground/30') : memberState?.status === 'done' ? 'bg-emerald-400' : memberState?.status === 'busy' ? 'bg-primary animate-pulse' : 'bg-muted-foreground/30';
              return <button key={tab.key} type="button" className={`flex items-center gap-2 border-b-2 px-4 py-2.5 text-sm transition-colors ${isActive ? 'border-primary text-primary font-medium' : 'border-transparent text-muted-foreground hover:text-foreground'}`} onClick={() => setActiveTab(tab.key)}><span className={`inline-block w-2 h-2 rounded-full shrink-0 ${dotColor}`} />{tab.label}</button>;
            })}
            <button type="button" onClick={() => setSidebarOpen((v) => !v)} className="ml-auto flex items-center gap-1.5 border-b-2 border-transparent px-4 py-2.5 text-sm text-muted-foreground hover:text-foreground transition-colors">
              <span className="text-xs">文件</span>
              {workspaceFiles.length > 0 && <span className="rounded-full bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">{workspaceFiles.length}</span>}
              <svg className={`h-3.5 w-3.5 transition-transform duration-200 ${sidebarOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
            </button>
          </div>

          <div className="flex flex-1 overflow-hidden">
            <div className="flex flex-1 flex-col overflow-hidden">
              <div className="flex-1 overflow-y-scroll px-4 py-6">
                <div className="mx-auto max-w-3xl">
                  {timelineItems.length === 0 && !showStreaming && (
                    <div className="py-20 text-center text-muted-foreground/50"><p className="text-sm">等待执行开始...</p></div>
                  )}
                  <TimelineBubble
                    items={timelineItems}
                    isStreaming={showStreaming}
                    activeClarifyId={activeTab === 'leader' ? activeClarifyId : undefined}
                    onClarifyAnswer={activeTab === 'leader' ? handleClarifyAnswer : undefined}
                  />
                  <div ref={logsEndRef} />
                </div>
              </div>
              {finalResult && (
                <div className="border-t border-border/50 bg-card/50">
                  <button type="button" onClick={() => setFinalResultExpanded((v) => !v)} className="mx-auto flex w-full max-w-3xl items-center gap-2 px-4 py-2.5 text-left transition-colors hover:bg-muted/30" aria-expanded={finalResultExpanded}>
                    <span className="inline-block w-2 h-2 rounded-full bg-emerald-400 shrink-0" /><span className="text-sm font-medium">🎉 最终结果</span><span className="text-xs text-muted-foreground/60">({finalResult.length} 字符)</span>
                    <svg className={`ml-auto h-4 w-4 shrink-0 text-muted-foreground/40 transition-transform duration-200 ${finalResultExpanded ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
                  </button>
                  {finalResultExpanded && <div className="mx-auto max-w-3xl px-4 pb-4"><div className="rounded-2xl border border-emerald-200/50 bg-card px-4 py-3"><div className="markdown-content text-sm leading-relaxed"><ReactMarkdown remarkPlugins={[remarkGfm]}>{finalResult}</ReactMarkdown></div></div></div>}
                </div>
              )}
            </div>
            {sidebarOpen && (
              <div className="w-64 flex-shrink-0 border-l bg-card/30 overflow-y-auto">
                <div className="p-3 border-b bg-card/50 flex items-center justify-between">
                  <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">工作空间</h3>
                  <button type="button" onClick={fetchWorkspaceFiles} className="text-xs text-muted-foreground/50 hover:text-muted-foreground transition-colors">刷新</button>
                </div>
                {workspaceFiles.length === 0 ? (
                  <div className="p-4 text-center text-xs text-muted-foreground/50">暂无文件</div>
                ) : (
                  <div className="divide-y divide-border/20">
                    {workspaceFiles.map((f) => (
                      <div key={f.path} className="px-3 py-2 flex items-center gap-2 text-xs">
                        <span className="shrink-0">{f.is_dir ? '📁' : '📄'}</span>
                        <span className="flex-1 truncate text-muted-foreground">{f.name}</span>
                        <span className="shrink-0 text-muted-foreground/40 text-[10px]">
                          {f.is_dir ? '' : f.size > 1024 ? `${(f.size / 1024).toFixed(1)}KB` : `${f.size}B`}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="border-t bg-card px-4 py-3">
            <div className="mx-auto flex max-w-3xl items-end gap-3">
              <textarea className="flex-1 resize-none rounded-xl border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground/50 focus:border-primary/30 focus:outline-none focus:ring-0" rows={1} placeholder="继续追问..." value={followUpInput} disabled={isFollowUpRunning || runState === 'running'} onChange={(e) => { followUpRef.current = e.target.value; setFollowUpInput(e.target.value); e.target.style.height = 'auto'; e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px'; }} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleFollowUp(); }}} />
              <button type="button" className="btn btn-primary shrink-0 text-sm" disabled={!followUpInput.trim() || isFollowUpRunning || runState === 'running'} onClick={() => handleFollowUp()}>{isFollowUpRunning ? '执行中...' : '发送'}</button>
            </div>
          </div>
        </>
      )}
    </div>
  );
};
