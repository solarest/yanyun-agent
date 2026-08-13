/**
 * 应用层 - Team 执行 Hook
 *
 * 从 TeamExecutionPage 抽出的全部执行编排逻辑：
 * - 目标执行 / 追问 / 澄清回复三条链路
 * - leader + member 双 SSE 流绑定与事件 → 时间线段状态更新
 * - localStorage 持久化活跃执行 + 刷新恢复（后端 SSE 重放全部事件）
 * - 工作空间文件轮询
 *
 * 页面只负责布局；时间线渲染见 @presentation/components/team/TeamTimeline。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTeamManagement } from '@application/services/useTeamManagement';
import { AgentEventStream } from '@infrastructure/api/eventStream';
import { buildTimeline, type TimelineSegment, type TimelineRenderItem } from '@presentation/components/team/TeamTimeline';
import type { TeamMember } from '@domain/entities/team';

export type RunState = 'idle' | 'running' | 'completed' | 'failed';

export interface MemberRunState {
  agentId: string;
  agentName: string;
  status: 'idle' | 'busy' | 'done';
  taskId?: string;
  taskDescription?: string;
  result?: string;
  segments: TimelineSegment[];
}

export interface TeamTab {
  key: string;
  label: string;
  role: 'leader' | 'member';
}

export interface WorkspaceFileEntry {
  name: string;
  path: string;
  is_dir: boolean;
  size: number;
  modified_at: number;
}

const TEAM_EXEC_KEY = 'activeTeamExecution';
const WORKSPACE_POLL_INTERVAL_MS = 3000;
/** 恢复时效：超过该时长的活跃执行视为陈旧 */
const RESTORE_STALE_MS = 30 * 60 * 1000;
/** 距底部小于该距离视为"在底部"，自动跟随滚动 */
const AUTO_SCROLL_THRESHOLD_PX = 120;

export const useTeamExecution = (teamId: string) => {
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
  const [isStreamingLeader, setIsStreamingLeader] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [workspaceFiles, setWorkspaceFiles] = useState<WorkspaceFileEntry[]>([]);
  const [followUpInput, setFollowUpInput] = useState('');
  const [isFollowUpRunning, setIsFollowUpRunning] = useState(false);
  // 当前活跃的澄清 toolCallId：仅末尾未回复的澄清框可交互，回复/新执行时清空
  const [activeClarifyId, setActiveClarifyId] = useState<string | null>(null);

  const streamRef = useRef<AgentEventStream | null>(null);
  const memberStreamsRef = useRef<Map<string, AgentEventStream>>(new Map());
  const logsEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const followUpRef = useRef('');
  const runningRef = useRef(false);
  // 当前 leader 会话 ID：首次执行从响应中获取，追问时回传以保持澄清链路上下文连续
  const leaderSessionIdRef = useRef<string | null>(null);
  const activeClarifyIdRef = useRef<string | null>(null);
  const restoredRef = useRef(false);

  const members: TeamMember[] = currentTeam?.members ?? [];
  const leader = members.find((m) => m.role === 'leader');
  const regularMembers = members.filter((m) => m.role === 'member');
  // ref 镜像：SSE handler（含恢复重连）需读取最新的成员列表，避免闭包 stale。
  // 在 effect 中同步（不在 render 期间写 ref，避免并发渲染下读到中间状态）
  const regularMembersRef = useRef(regularMembers);
  useEffect(() => {
    regularMembersRef.current = regularMembers;
  }, [regularMembers]);

  useEffect(() => {
    if (teamId) fetchTeam(teamId);
  }, [teamId, fetchTeam]);

  // 卸载时断开全部流
  useEffect(() => {
    return () => {
      streamRef.current?.disconnect();
      memberStreamsRef.current.forEach((s) => s.disconnect());
    };
  }, []);

  // ── Workspace file polling ──
  const fetchWorkspaceFiles = useCallback(async () => {
    if (!teamId) return;
    try {
      const res = await fetch(`/api/teams/${teamId}/workspace-files?path=${encodeURIComponent(workspace)}`);
      const data = await res.json();
      setWorkspaceFiles(data.files || []);
    } catch {
      /* ignore */
    }
  }, [teamId, workspace]);

  useEffect(() => {
    if (runState !== 'idle' && sidebarOpen) {
      fetchWorkspaceFiles();
      const interval = setInterval(fetchWorkspaceFiles, WORKSPACE_POLL_INTERVAL_MS);
      return () => clearInterval(interval);
    }
  }, [runState, sidebarOpen, fetchWorkspaceFiles]);

  const allTabs: TeamTab[] = [
    { key: 'leader', label: leader?.agent_name || 'Leader', role: 'leader' },
    ...regularMembers.map((m) => ({
      key: m.agent_id,
      label: m.agent_name || m.agent_id,
      role: 'member' as const,
    })),
  ];

  const currentSegments = activeTab === 'leader'
    ? leaderSegments
    : memberStates.get(activeTab)?.segments ?? [];

  // ── Segment mutation helpers ──
  const pushLeaderSegment = useCallback((seg: TimelineSegment) => {
    setLeaderSegments((prev) => [...prev, seg]);
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

  const disconnectMemberStreams = useCallback(() => {
    memberStreamsRef.current.forEach((s) => s.disconnect());
    memberStreamsRef.current.clear();
  }, []);

  // ── Stream binding ──
  const bindMemberStream = useCallback((agentId: string, taskId: string) => {
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
  const saveActiveExecution = useCallback((execId: string, sessionId: string) => {
    if (!teamId) return;
    try {
      localStorage.setItem(TEAM_EXEC_KEY, JSON.stringify({
        teamId, executionId: execId, sessionId, timestamp: Date.now(),
      }));
    } catch { /* ignore */ }
  }, [teamId]);

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
      if (p.task_id) bindMemberStream(p.agent_id, p.task_id);
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
      disconnectMemberStreams();
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
      disconnectMemberStreams();
      addLeaderSystem(`❌ 执行失败: ${p.error}`); setRunState('failed');
      clearActiveExecution();
    });
  }, [pushLeaderSegment, appendLeaderThinking, appendLeaderText, addLeaderSystem, bindMemberStream, clearActiveExecution, disconnectMemberStreams]);

  // ── 刷新恢复：复用 chat 的 localStorage + SSE replay 模式 ──
  // 后端 SSE 在全新连接时重放该 task 的全部事件，故重连后用同一套 handler 重建 timeline，
  // 与运行时渲染完全一致；澄清等待中（未 clearActiveExecution）也会恢复澄清框。
  useEffect(() => {
    if (!teamId) return;
    let entry: { teamId?: string; executionId?: string; sessionId?: string; timestamp?: number } | null = null;
    try {
      const raw = localStorage.getItem(TEAM_EXEC_KEY);
      if (raw) entry = JSON.parse(raw);
    } catch { /* ignore */ }
    if (!entry || entry.teamId !== teamId) return;
    // 超过 30min 视为陈旧，不恢复
    if (Date.now() - (entry.timestamp || 0) > RESTORE_STALE_MS) { clearActiveExecution(); return; }
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
  }, [teamId, bindLeaderStream, addLeaderSystem, clearActiveExecution]);

  // 追问输入：state 供渲染，ref 供 handleFollowUp 同步读取（快速输入+回车时不依赖已提交的 state）
  const handleFollowUpInputChange = useCallback((value: string) => {
    followUpRef.current = value;
    setFollowUpInput(value);
  }, []);

  // ── Execute ──
  const handleExecute = useCallback(async () => {
    if (!goal.trim() || !teamId || runningRef.current) return;
    runningRef.current = true;
    setRunState('running'); setIsStreamingLeader(true);
    setLeaderSegments([]); setMemberStates(new Map());
    setFinalResult('');
    activeClarifyIdRef.current = null; setActiveClarifyId(null);
    disconnectMemberStreams();

    setLeaderSegments([{ type: 'system', content: `开始执行: ${goal}` }]);

    const result = await executeTeam(teamId, goal.trim());
    if (!result) {
      runningRef.current = false;
      setRunState('failed'); setIsStreamingLeader(false); addLeaderSystem('❌ 执行启动失败'); return;
    }

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
  }, [teamId, goal, executeTeam, addLeaderSystem, saveActiveExecution, bindLeaderStream, disconnectMemberStreams]);

  // ── Follow-up ──
  const handleFollowUp = useCallback(async (answer?: string) => {
    const q = (answer ?? followUpRef.current).trim();
    if (!q || !teamId || runningRef.current) return;
    runningRef.current = true; setFollowUpInput(''); followUpRef.current = '';
    activeClarifyIdRef.current = null; setActiveClarifyId(null);
    setIsFollowUpRunning(true); setRunState('running'); setIsStreamingLeader(true);
    addLeaderSystem(`💬 追问: ${q}`);

    const result = await executeTeam(teamId, q, undefined, leaderSessionIdRef.current || undefined);
    if (!result) { runningRef.current = false; setIsFollowUpRunning(false); setRunState('failed'); addLeaderSystem('❌ 追问执行失败'); return; }

    const execId = result.execution_id; setExecutionId(execId); if (result.workspace) setWorkspace(result.workspace);
    saveActiveExecution(execId, result.session_id || leaderSessionIdRef.current || execId);
    streamRef.current?.disconnect();
    const ls = new AgentEventStream('', execId);
    streamRef.current = ls;
    bindLeaderStream(ls, { execId, followUpGoal: q });
    ls.connect();
  }, [teamId, executeTeam, addLeaderSystem, saveActiveExecution, bindLeaderStream]);

  // 澄清框回复：复用追问链路（带 session_id），清空活跃澄清标记使该框转为已回复态
  const handleClarifyAnswer = useCallback((answer: string) => {
    activeClarifyIdRef.current = null;
    setActiveClarifyId(null);
    handleFollowUp(answer);
  }, [handleFollowUp]);

  // ── 派生渲染数据 ──
  const timelineItems = useMemo<TimelineRenderItem[]>(
    () => buildTimeline(currentSegments),
    [currentSegments],
  );
  const showStreaming = activeTab === 'leader' && isStreamingLeader;

  // ── 自动滚动：仅在用户位于底部时跟随（流式增长用 auto，避免 smooth 动画堆积） ──
  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;
    const distanceFromBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight;
    if (distanceFromBottom < AUTO_SCROLL_THRESHOLD_PX) {
      logsEndRef.current?.scrollIntoView({ behavior: 'auto', block: 'end' });
    }
  }, [leaderSegments, memberStates]);

  return {
    currentTeam,
    teamLoading,
    teamError,
    goal,
    setGoal,
    runState,
    executionId,
    activeTab,
    setActiveTab,
    allTabs,
    memberStates,
    timelineItems,
    showStreaming,
    activeClarifyId,
    finalResult,
    finalResultExpanded,
    setFinalResultExpanded,
    sidebarOpen,
    setSidebarOpen,
    workspaceFiles,
    fetchWorkspaceFiles,
    followUpInput,
    handleFollowUpInputChange,
    isFollowUpRunning,
    handleExecute,
    handleFollowUp,
    handleClarifyAnswer,
    scrollContainerRef,
    logsEndRef,
  };
};
