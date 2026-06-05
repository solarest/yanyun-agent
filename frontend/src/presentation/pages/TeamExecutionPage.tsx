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
  type: 'thinking' | 'text' | 'tool_group' | 'system';
  content?: string;
  tools?: ToolTimelineItem[];
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

/** 时间线气泡 — 渲染 buildTimeline 的结果 */
const TimelineBubble: React.FC<{ items: TimelineRenderItem[]; isStreaming: boolean }> = ({ items, isStreaming }) => {
  if (items.length === 0) {
    return isStreaming ? (
      <div className="rounded-2xl border border-border/50 bg-card px-4 py-3">
        <span className="inline-block h-4 w-1 animate-pulse bg-current" />
      </div>
    ) : null;
  }

  return (
    <div className="rounded-2xl border border-border/50 bg-card px-4 py-3">
      {items.map((item, idx) => {
        if (item.type === 'system') {
          return <SystemEntry key={`s-${idx}`} content={item.content!} />;
        }
        if (item.type === 'thinking') {
          return <ThinkingBlock key={`t-${idx}`} content={item.content!} isStreaming={isStreaming} />;
        }
        if (item.type === 'tool_group') {
          return <ToolCallGroup key={`g-${idx}`} items={item.tools!} isStreaming={isStreaming} />;
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
  const [activeTab, setActiveTab] = useState<string>('leader');
  const [leaderSegments, setLeaderSegments] = useState<TimelineSegment[]>([]);
  const [memberStates, setMemberStates] = useState<Map<string, MemberRunState>>(new Map());
  const [finalResult, setFinalResult] = useState('');
  const [finalResultExpanded, setFinalResultExpanded] = useState(false);
  const [goalInputFocused, setGoalInputFocused] = useState(false);
  const [isStreamingLeader, setIsStreamingLeader] = useState(false);
  const [sidebarResults, setSidebarResults] = useState<Array<{ goal: string; result: string; id: string }>>([]);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [followUpInput, setFollowUpInput] = useState('');
  const [isFollowUpRunning, setIsFollowUpRunning] = useState(false);

  const streamRef = useRef<AgentEventStream | null>(null);
  const memberStreamsRef = useRef<Map<string, AgentEventStream>>(new Map());
  const logsEndRef = useRef<HTMLDivElement>(null);
  const followUpRef = useRef('');
  const runningRef = useRef(false);

  useEffect(() => { if (id) fetchTeam(id); }, [id, fetchTeam]);
  useEffect(() => {
    return () => { streamRef.current?.disconnect(); memberStreamsRef.current.forEach((s) => s.disconnect()); };
  }, []);
  useEffect(() => { logsEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [leaderSegments]);

  const members: TeamMember[] = currentTeam?.members ?? [];
  const leader = members.find((m) => m.role === 'leader');
  const regularMembers = members.filter((m) => m.role === 'member');

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

  // ── Execute ──
  const handleExecute = async () => {
    if (!goal.trim() || !id) return;
    setRunState('running'); setIsStreamingLeader(true);
    setLeaderSegments([]); setMemberStates(new Map());
    setFinalResult(''); runningRef.current = false;

    const leaderName = leader?.agent_name || 'Leader';
    setLeaderSegments([{ type: 'system', content: `开始执行: ${goal}` }]);

    const result = await executeTeam(id, goal.trim());
    if (!result) { setRunState('failed'); setIsStreamingLeader(false); addLeaderSystem('❌ 执行启动失败'); return; }

    const execId = result.execution_id;
    setExecutionId(execId);
    addLeaderSystem(`执行 ID: ${execId}`);

    streamRef.current?.disconnect();
    const ls = new AgentEventStream('', execId);
    streamRef.current = ls;

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
    });
    ls.on('thinking:chunk', (p: any) => { if (p.text) appendLeaderThinking(p.text); });
    ls.on('llm:chunk', (p: any) => { if (p.text) appendLeaderText(p.text); });

    ls.on('team:task:assigned', (p: any) => {
      const mName = regularMembers.find((m) => m.agent_id === p.agent_id)?.agent_name || p.agent_id;
      addLeaderSystem(`📤 分配任务给 ${mName}:\n${p.description || ''}`);
      setMemberStates((prev) => {
        const next = new Map(prev);
        next.set(p.agent_id, { agentId: p.agent_id, agentName: mName, status: 'busy', taskId: p.task_id, taskDescription: p.description, segments: [{ type: 'system', content: `📥 收到任务:\n${p.description || ''}` }] });
        return next;
      });
      if (p.task_id) bindMemberStream(p.agent_id, p.task_id, mName);
    });
    ls.on('team:task:reported', (p: any) => {
      const mName = regularMembers.find((m) => m.agent_id === p.agent_id)?.agent_name || p.agent_id;
      addLeaderSystem(`${p.status === 'completed' ? '✅' : '❌'} ${mName} 完成`);
      setMemberStates((prev) => { const next = new Map(prev); const e = next.get(p.agent_id); if (e) next.set(p.agent_id, { ...e, status: 'done', result: p.result }); return next; });
    });
    ls.on('team:task:updated', (p: any) => { addLeaderSystem(`📋 任务列表更新 — ${p.task_count} 项`); });
    ls.on('task:completed', () => { addLeaderSystem('✅ Leader 执行完成'); });

    ls.on('team:execution:completed', (p: any) => {
      setIsStreamingLeader(false); setIsFollowUpRunning(false);
      addLeaderSystem('🎉 团队执行完成!');
      setFinalResult(p.result || ''); setFinalResultExpanded(true); setRunState('completed');
      setSidebarResults((prev) => [...prev, { goal: goal.trim(), result: p.result || '', id: execId }]);
      setSidebarOpen(true);
    });
    ls.on('team:execution:failed', (p: any) => {
      setIsStreamingLeader(false); setIsFollowUpRunning(false);
      addLeaderSystem(`❌ 执行失败: ${p.error}`); setRunState('failed');
    });
    ls.connect();
  };

  // ── Follow-up ──
  const handleFollowUp = useCallback(async () => {
    const q = followUpRef.current.trim();
    if (!q || !id || runningRef.current) return;
    runningRef.current = true; setFollowUpInput(''); followUpRef.current = '';
    setIsFollowUpRunning(true); setRunState('running'); setIsStreamingLeader(true);
    addLeaderSystem(`💬 追问: ${q}`);

    const result = await executeTeam(id, q);
    if (!result) { runningRef.current = false; setIsFollowUpRunning(false); setRunState('failed'); addLeaderSystem('❌ 追问执行失败'); return; }

    const execId = result.execution_id; setExecutionId(execId);
    streamRef.current?.disconnect();
    const ls = new AgentEventStream('', execId);
    streamRef.current = ls;

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
    });
    ls.on('thinking:chunk', (p: any) => { if (p.text) appendLeaderThinking(p.text); });
    ls.on('llm:chunk', (p: any) => { if (p.text) appendLeaderText(p.text); });
    ls.on('team:task:assigned', (p: any) => {
      const mName = regularMembers.find((m) => m.agent_id === p.agent_id)?.agent_name || p.agent_id;
      addLeaderSystem(`📤 分配任务给 ${mName}:\n${p.description || ''}`);
      if (p.task_id) bindMemberStream(p.agent_id, p.task_id, mName);
    });
    ls.on('team:task:reported', (p: any) => { addLeaderSystem(`${p.status === 'completed' ? '✅' : '❌'} ${regularMembers.find((m) => m.agent_id === p.agent_id)?.agent_name || p.agent_id} 完成`); });
    ls.on('team:task:updated', (p: any) => { addLeaderSystem(`📋 任务列表更新 — ${p.task_count} 项`); });
    ls.on('task:completed', () => { addLeaderSystem('✅ Leader 执行完成'); });
    ls.on('team:execution:completed', (p: any) => {
      runningRef.current = false; setIsStreamingLeader(false); setIsFollowUpRunning(false);
      addLeaderSystem('🎉 追问执行完成!');
      setFinalResult(p.result || ''); setFinalResultExpanded(true); setRunState('completed');
      setSidebarResults((prev) => [...prev, { goal: q, result: p.result || '', id: execId }]);
    });
    ls.on('team:execution:failed', (p: any) => {
      runningRef.current = false; setIsStreamingLeader(false); setIsFollowUpRunning(false);
      addLeaderSystem(`❌ 追问失败: ${p.error}`); setRunState('failed');
    });
    ls.connect();
  }, [id, leader, executeTeam, pushLeaderSegment, appendLeaderThinking, appendLeaderText, addLeaderSystem, regularMembers, bindMemberStream]);

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
            {sidebarResults.length > 0 && (
              <button type="button" onClick={() => setSidebarOpen((v) => !v)} className="ml-auto flex items-center gap-1.5 border-b-2 border-transparent px-4 py-2.5 text-sm text-muted-foreground hover:text-foreground transition-colors">
                <span className="text-xs">结果</span><span className="rounded-full bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">{sidebarResults.length}</span>
                <svg className={`h-3.5 w-3.5 transition-transform duration-200 ${sidebarOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
              </button>
            )}
          </div>

          <div className="flex flex-1 overflow-hidden">
            <div className="flex flex-1 flex-col overflow-hidden">
              <div className="flex-1 overflow-y-scroll px-4 py-6">
                <div className="mx-auto max-w-3xl">
                  {timelineItems.length === 0 && !showStreaming && (
                    <div className="py-20 text-center text-muted-foreground/50"><p className="text-sm">等待执行开始...</p></div>
                  )}
                  <TimelineBubble items={timelineItems} isStreaming={showStreaming} />
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
            {sidebarOpen && sidebarResults.length > 0 && (
              <div className="w-80 flex-shrink-0 border-l bg-card/30 overflow-y-auto">
                <div className="p-3 border-b bg-card/50"><h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">执行结果</h3></div>
                <div className="divide-y divide-border/30">
                  {sidebarResults.map((item) => (
                    <div key={item.id} className="p-3">
                      <p className="text-[11px] font-medium text-muted-foreground/60 mb-1">{item.goal}</p>
                      <div className="text-xs leading-relaxed markdown-content max-h-60 overflow-y-auto"><ReactMarkdown remarkPlugins={[remarkGfm]}>{item.result.length > 3000 ? item.result.slice(0, 3000) + '...' : item.result}</ReactMarkdown></div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="border-t bg-card px-4 py-3">
            <div className="mx-auto flex max-w-3xl items-end gap-3">
              <textarea className="flex-1 resize-none rounded-xl border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground/50 focus:border-primary/30 focus:outline-none focus:ring-0" rows={1} placeholder="继续追问..." value={followUpInput} disabled={isFollowUpRunning || runState === 'running'} onChange={(e) => { followUpRef.current = e.target.value; setFollowUpInput(e.target.value); e.target.style.height = 'auto'; e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px'; }} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleFollowUp(); }}} />
              <button type="button" className="btn btn-primary shrink-0 text-sm" disabled={!followUpInput.trim() || isFollowUpRunning || runState === 'running'} onClick={handleFollowUp}>{isFollowUpRunning ? '执行中...' : '发送'}</button>
            </div>
          </div>
        </>
      )}
    </div>
  );
};
