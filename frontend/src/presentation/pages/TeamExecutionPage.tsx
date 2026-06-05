/**
 * 表现层 - Team 执行页
 *
 * 聊天式界面 + 多 Agent Tab 展示，样式与 Agent 对话页统一：
 * - 左侧：团队目标 + 执行控制
 * - 主区域：Tab 栏切换不同 Agent 的运行状态
 * - 每个 Tab 内展示该 Agent 的消息流（工具调用、输出、结果）
 */
import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useTeamManagement } from '@application/services/useTeamManagement';
import { AgentEventStream } from '@infrastructure/api/eventStream';
import { ToolCallCard } from '@presentation/components/chat/ToolCallCard';
import { ThinkingBlock } from '@presentation/components/chat/ThinkingBlock';
import type { TeamMember } from '@domain/entities/team';

// ═══════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════

type RunState = 'idle' | 'running' | 'completed' | 'failed';

interface LogEntry {
  id: string;
  timestamp: string;
  agentId: string;
  agentName: string;
  type: 'tool_call' | 'tool_result' | 'text' | 'thinking' | 'system';
  toolCallId?: string;
  toolName?: string;
  toolInput?: string;
  toolStatus?: string;
  toolResult?: string;
  content: string;
  status?: 'success' | 'error' | 'running';
}

interface MemberRunState {
  agentId: string;
  agentName: string;
  status: 'idle' | 'busy' | 'done';
  taskId?: string;
  taskDescription?: string;
  result?: string;
  logs: LogEntry[];
}

// ═══════════════════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════════════════

function getToolLabel(name: string, input: Record<string, unknown> | undefined): string {
  switch (name) {
    case 'update_team_tasks': {
      const tasks = input?.tasks as Array<unknown> | undefined;
      return `更新任务列表 (${tasks?.length || 0} 项)`;
    }
    case 'assign_team_task':
      return `分配任务 → ${input?.agent_id}: ${String(input?.task_description || '').slice(0, 60)}`;
    case 'check_team_reports':
      return '检查成员报告';
    case 'web_search':
      return `搜索: ${String(input?.query || '').slice(0, 60)}`;
    case 'web_fetch':
      return `获取: ${String(input?.url || '').slice(0, 60)}`;
    case 'report_team_task':
      return '上报结果';
    default:
      return name;
  }
}

const PHASE_LABELS: Record<string, string> = {
  idle: '空闲',
  running: '执行中',
  completed: '已完成',
  failed: '失败',
};

// ═══════════════════════════════════════════════════════
// Sub-components
// ═══════════════════════════════════════════════════════

/** 头像 — 与 MessageBubble 中 Avatar 保持一致 */
const Avatar: React.FC<{ letter: string; variant?: 'leader' | 'member' | 'system' }> = ({
  letter,
  variant = 'member',
}) => {
  const colors = variant === 'leader'
    ? 'bg-primary/10 border-primary/20 text-primary/70'
    : variant === 'system'
      ? 'bg-muted border-border text-muted-foreground'
      : 'bg-muted border-border text-muted-foreground';

  return (
    <div className={`flex-shrink-0 w-7 h-7 rounded-full border flex items-center justify-center ${colors}`}>
      <span className="text-xs font-bold">{letter.charAt(0).toUpperCase()}</span>
    </div>
  );
};

/** 系统消息 — 居中 pill */
const SystemPill: React.FC<{ content: string }> = ({ content }) => (
  <div className="flex justify-center py-1">
    <span className="rounded-full bg-secondary/50 px-3 py-1 text-xs text-muted-foreground">
      {content}
    </span>
  </div>
);

/** Log 气泡 — 时间线布局，匹配 MessageBubble 风格 */
const LogBubble: React.FC<{ entry: LogEntry }> = ({ entry }) => {
  const isTool = entry.type === 'tool_call' || entry.type === 'tool_result';
  const isThinking = entry.type === 'thinking';
  const isSystem = entry.type === 'system';

  if (isSystem) {
    return <SystemPill content={entry.content} />;
  }

  if (isThinking) {
    return (
      <div className="relative flex gap-3 pb-1">
        <Avatar letter={entry.agentName} />
        <div className="flex-1 min-w-0">
          <ThinkingBlock content={entry.content} isStreaming={false} />
        </div>
      </div>
    );
  }

  if (isTool) {
    return (
      <div className="relative flex gap-3 pb-1">
        <Avatar letter={entry.agentName} />
        <div className="flex-1 min-w-0">
          <div className="rounded-2xl border border-border/50 bg-card px-4 py-2.5">
            <div className="mb-1.5 flex items-center gap-2 text-xs">
              <span className="font-medium text-foreground/80">{entry.agentName}</span>
              <span className="text-muted-foreground/50">{entry.timestamp}</span>
            </div>
            <ToolCallCard
              name={entry.toolName || entry.content}
              status={entry.toolStatus || (entry.status === 'running' ? 'running' : entry.status === 'error' ? 'error' : 'success')}
              result={entry.toolResult}
              input={entry.toolInput ? JSON.parse(entry.toolInput) : undefined}
              isStreaming={entry.status === 'running'}
            />
          </div>
        </div>
      </div>
    );
  }

  // text entry
  return (
    <div className="relative flex gap-3 pb-5">
      <Avatar letter={entry.agentName} />
      <div className="flex-1 min-w-0">
        <div className="rounded-2xl border border-border/50 bg-card px-4 py-3">
          <div className="mb-1.5 flex items-center gap-2 text-xs">
            <span className="font-medium text-foreground/80">{entry.agentName}</span>
            <span className="text-muted-foreground/50">{entry.timestamp}</span>
          </div>
          <div className="markdown-content text-sm leading-relaxed">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {entry.content}
            </ReactMarkdown>
          </div>
        </div>
      </div>
    </div>
  );
};

/** 状态徽章 */
const StatusBadge: React.FC<{ status: string }> = ({ status }) => {
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

// ═══════════════════════════════════════════════════════
// Main Component
// ═══════════════════════════════════════════════════════

export const TeamExecutionPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const { currentTeam, fetchTeam, executeTeam, isLoading: teamLoading, error: teamError } = useTeamManagement();

  // ── State ──
  const [goal, setGoal] = useState('');
  const [runState, setRunState] = useState<RunState>('idle');
  const [executionId, setExecutionId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<string>('leader');
  const [leaderLogs, setLeaderLogs] = useState<LogEntry[]>([]);
  const [memberStates, setMemberStates] = useState<Map<string, MemberRunState>>(new Map());
  const [finalResult, setFinalResult] = useState('');
  const [finalResultExpanded, setFinalResultExpanded] = useState(false);
  const [goalInputFocused, setGoalInputFocused] = useState(false);

  // Refs
  const streamRef = useRef<AgentEventStream | null>(null);
  const memberStreamsRef = useRef<Map<string, AgentEventStream>>(new Map());
  const logsEndRef = useRef<HTMLDivElement>(null);

  // ── Init ──
  useEffect(() => { if (id) fetchTeam(id); }, [id, fetchTeam]);

  useEffect(() => {
    return () => {
      streamRef.current?.disconnect();
      memberStreamsRef.current.forEach((s) => s.disconnect());
    };
  }, []);

  // ── Auto-scroll ──
  useEffect(() => { logsEndRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [leaderLogs]);

  // ── Derived ──
  const members: TeamMember[] = currentTeam?.members ?? [];
  const leader = members.find((m) => m.role === 'leader');
  const regularMembers = members.filter((m) => m.role === 'member');

  const allTabs = [
    { key: 'leader', label: leader?.agent_name || 'Leader', agentId: leader?.agent_id || '', role: 'leader' as const },
    ...regularMembers.map((m) => ({
      key: m.agent_id,
      label: m.agent_name || m.agent_id,
      agentId: m.agent_id,
      role: 'member' as const,
    })),
  ];

  const currentLogs = activeTab === 'leader'
    ? leaderLogs
    : memberStates.get(activeTab)?.logs ?? [];

  // ── Helpers ──
  const addLeaderLog = useCallback((entry: Omit<LogEntry, 'id' | 'timestamp'>) => {
    const log: LogEntry = {
      ...entry,
      id: Math.random().toString(36).slice(2, 10),
      timestamp: new Date().toLocaleTimeString(),
    };
    setLeaderLogs((prev) => [...prev, log]);
  }, []);

  const addMemberLog = useCallback((agentId: string, entry: Omit<LogEntry, 'id' | 'timestamp'>) => {
    const log: LogEntry = {
      ...entry,
      id: Math.random().toString(36).slice(2, 10),
      timestamp: new Date().toLocaleTimeString(),
    };
    setMemberStates((prev) => {
      const next = new Map(prev);
      const existing = next.get(agentId);
      next.set(agentId, {
        ...(existing || { agentId, agentName: '', status: 'idle', logs: [] }),
        logs: [...(existing?.logs ?? []), log],
      });
      return next;
    });
  }, []);

  const connectMemberStream = useCallback((agentId: string, taskId: string, agentName: string) => {
    memberStreamsRef.current.get(agentId)?.disconnect();

    const stream = new AgentEventStream('', taskId);
    memberStreamsRef.current.set(agentId, stream);

    stream.on('tool:call', (payload: any) => {
      addMemberLog(agentId, {
        agentId, agentName,
        type: 'tool_call',
        toolCallId: payload.toolCallId,
        toolName: payload.toolName,
        toolInput: JSON.stringify(payload.input),
        toolStatus: 'running',
        content: getToolLabel(payload.toolName, payload.input),
        status: 'running',
      });
    });

    stream.on('tool:result', (payload: any) => {
      const output = (payload.output || '').slice(0, 3000);
      addMemberLog(agentId, {
        agentId, agentName,
        type: 'tool_result',
        toolCallId: payload.toolCallId,
        toolName: payload.toolName,
        toolStatus: payload.status === 'success' ? 'success' : 'error',
        toolResult: output,
        content: getToolLabel(payload.toolName, undefined),
        status: payload.status === 'success' ? 'success' : 'error',
      });
    });

    stream.on('thinking:chunk', (_payload: any) => {
      // Thinking handled through accumulated segments
    });

    stream.on('llm:chunk', (payload: any) => {
      setMemberStates((prev) => {
        const next = new Map(prev);
        const existing = next.get(agentId);
        const logs = existing?.logs ?? [];
        const lastLog = logs[logs.length - 1];
        if (lastLog?.type === 'text' && lastLog.agentId === agentId) {
          const updatedLogs = [...logs];
          updatedLogs[updatedLogs.length - 1] = {
            ...lastLog,
            content: lastLog.content + (payload.text || ''),
          };
          next.set(agentId, { ...(existing || { agentId, agentName, status: 'idle', logs: [] }), logs: updatedLogs });
        } else {
          next.set(agentId, {
            ...(existing || { agentId, agentName, status: 'idle', logs: [] }),
            logs: [...logs, {
              id: Math.random().toString(36).slice(2, 10),
              timestamp: new Date().toLocaleTimeString(),
              agentId,
              agentName,
              type: 'text',
              content: payload.text || '',
            }],
          });
        }
        return next;
      });
    });

    stream.on('task:completed', () => {
      addMemberLog(agentId, {
        agentId, agentName, type: 'system',
        content: '✅ 任务执行完成',
      });
      setMemberStates((prev) => {
        const next = new Map(prev);
        const existing = next.get(agentId);
        if (existing) next.set(agentId, { ...existing, status: 'done' });
        return next;
      });
    });

    stream.on('task:failed', (payload: any) => {
      addMemberLog(agentId, {
        agentId, agentName, type: 'system',
        content: `❌ 任务失败: ${payload.error || 'Unknown'}`,
      });
      setMemberStates((prev) => {
        const next = new Map(prev);
        const existing = next.get(agentId);
        if (existing) next.set(agentId, { ...existing, status: 'done' });
        return next;
      });
    });

    stream.connect();
  }, [addMemberLog]);

  // ── Execute ──
  const handleExecute = async () => {
    if (!goal.trim() || !id) return;

    setRunState('running');
    setLeaderLogs([]);
    setMemberStates(new Map());
    setFinalResult('');

    const leaderName = leader?.agent_name || 'Leader';
    addLeaderLog({ agentId: 'system', agentName: 'System', type: 'system', content: `开始执行: ${goal}` });

    const result = await executeTeam(id, goal.trim());
    if (!result) {
      setRunState('failed');
      addLeaderLog({ agentId: 'system', agentName: 'System', type: 'system', content: '❌ 执行启动失败' });
      return;
    }

    const execId = result.execution_id;
    setExecutionId(execId);
    addLeaderLog({ agentId: 'system', agentName: 'System', type: 'system', content: `执行 ID: ${execId}` });

    // ── Leader SSE ──
    const leaderStream = new AgentEventStream('', execId);
    streamRef.current = leaderStream;

    // Tool calls by leader
    leaderStream.on('tool:call', (payload: any) => {
      const name = payload.toolName;
      addLeaderLog({
        agentId: leader?.agent_id || '', agentName: leaderName,
        type: 'tool_call',
        toolCallId: payload.toolCallId,
        toolName: name,
        toolInput: JSON.stringify(payload.input),
        toolStatus: 'running',
        content: getToolLabel(name, payload.input),
        status: 'running',
      });
    });

    leaderStream.on('tool:result', (payload: any) => {
      const output = (payload.output || '').slice(0, 3000);
      addLeaderLog({
        agentId: leader?.agent_id || '', agentName: leaderName,
        type: 'tool_result',
        toolCallId: payload.toolCallId,
        toolName: payload.toolName,
        toolStatus: payload.status === 'success' ? 'success' : 'error',
        toolResult: output,
        content: getToolLabel(payload.toolName, undefined),
        status: payload.status === 'success' ? 'success' : 'error',
      });
    });

    // Leader text output (final synthesis)
    leaderStream.on('llm:chunk', (payload: any) => {
      setLeaderLogs((prev) => {
        const last = prev[prev.length - 1];
        if (last?.type === 'text' && last.agentId === leader?.agent_id) {
          return prev.map((l, i) =>
            i === prev.length - 1 ? { ...l, content: l.content + (payload.text || '') } : l
          );
        }
        return [...prev, {
          id: Math.random().toString(36).slice(2, 10),
          timestamp: new Date().toLocaleTimeString(),
          agentId: leader?.agent_id || '',
          agentName: leaderName,
          type: 'text',
          content: payload.text || '',
        }];
      });
    });

    // Team events on leader stream
    leaderStream.on('team:task:assigned', (payload: any) => {
      const mName = regularMembers.find((m) => m.agent_id === payload.agent_id)?.agent_name || payload.agent_id;
      addLeaderLog({
        agentId: 'system', agentName: 'System', type: 'system',
        content: `📤 分配任务给 ${mName}: ${(payload.description || '').slice(0, 100)}`,
      });

      // Init member state + connect member SSE
      setMemberStates((prev) => {
        const next = new Map(prev);
        next.set(payload.agent_id, {
          agentId: payload.agent_id,
          agentName: mName,
          status: 'busy',
          taskId: payload.task_id,
          taskDescription: payload.description,
          logs: [{
            id: 'start',
            timestamp: new Date().toLocaleTimeString(),
            agentId: payload.agent_id,
            agentName: mName,
            type: 'system',
            content: `📥 收到任务: ${(payload.description || '').slice(0, 150)}`,
          }],
        });
        return next;
      });

      if (payload.task_id) {
        connectMemberStream(payload.agent_id, payload.task_id, mName);
      }
    });

    leaderStream.on('team:task:reported', (payload: any) => {
      const mName = regularMembers.find((m) => m.agent_id === payload.agent_id)?.agent_name || payload.agent_id;
      const statusIcon = payload.status === 'completed' ? '✅' : '❌';
      addLeaderLog({
        agentId: 'system', agentName: 'System', type: 'system',
        content: `${statusIcon} ${mName} 完成: ${(payload.result || '').slice(0, 200)}`,
      });

      setMemberStates((prev) => {
        const next = new Map(prev);
        const existing = next.get(payload.agent_id);
        next.set(payload.agent_id, {
          ...(existing || { agentId: payload.agent_id, agentName: mName, status: 'done', logs: [] }),
          status: 'done',
          result: payload.result,
        });
        return next;
      });
    });

    leaderStream.on('team:task:updated', (payload: any) => {
      addLeaderLog({
        agentId: 'system', agentName: 'System', type: 'system',
        content: `📋 任务列表更新 — ${payload.task_count} 项`,
      });
    });

    leaderStream.on('task:completed', () => {
      addLeaderLog({ agentId: 'system', agentName: 'System', type: 'system', content: '✅ Leader 执行完成' });
    });

    leaderStream.on('team:execution:completed', (payload: any) => {
      addLeaderLog({ agentId: 'system', agentName: 'System', type: 'system', content: '🎉 团队执行完成!' });
      setFinalResult(payload.result || '');
      setFinalResultExpanded(true);
      setRunState('completed');
    });

    leaderStream.on('team:execution:failed', (payload: any) => {
      addLeaderLog({ agentId: 'system', agentName: 'System', type: 'system', content: `❌ 执行失败: ${payload.error}` });
      setRunState('failed');
    });

    leaderStream.connect();
  };

  // ── Render ──
  return (
    <div className="flex h-screen flex-col">
      {/* ── Header — 匹配 ChatHeader 样式 ── */}
      <header className="flex items-center justify-between border-b bg-card px-4 py-3">
        <div className="flex items-center gap-3">
          <Link
            to={`/teams/${id}`}
            className="text-sm text-muted-foreground hover:text-foreground"
          >
            &larr; 返回
          </Link>
          <div className="h-5 w-px bg-border" />
          <div>
            <h2 className="text-sm font-semibold">{currentTeam?.name ?? '加载中...'}</h2>
          </div>
          <StatusBadge status={runState} />
          {executionId && (
            <span className="text-xs text-muted-foreground/50 font-mono">{executionId}</span>
          )}
        </div>
        <div className="flex items-center gap-3">
          {runState === 'running' && (
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span className="h-2 w-2 animate-pulse rounded-full bg-primary" />
              执行中...
            </span>
          )}
        </div>
      </header>

      {/* ── Goal Input (when idle) — 匹配 MessageInput 风格 ── */}
      {runState === 'idle' && (
        <div className="flex-1 flex flex-col items-center justify-center p-4">
          <div className="w-full max-w-2xl">
            <h2 className="mb-6 text-center text-xl font-semibold">团队目标</h2>
            <div className={`rounded-2xl border bg-card transition-colors ${
              goalInputFocused ? 'border-primary/30 shadow-sm' : 'border-border'
            }`}>
              <textarea
                className="w-full resize-none bg-transparent px-4 py-3 text-sm placeholder:text-muted-foreground/50 focus:outline-none"
                rows={4}
                placeholder="描述你的团队目标，Leader 将自动拆解为子任务并分配给成员..."
                value={goal}
                onFocus={() => setGoalInputFocused(true)}
                onBlur={() => setGoalInputFocused(false)}
                onChange={(e) => setGoal(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                    e.preventDefault();
                    handleExecute();
                  }
                }}
              />
              <div className="flex items-center justify-between border-t border-border/50 px-3 py-2">
                <span className="text-[10px] text-muted-foreground/40">
                  ⌘ + Enter 开始执行
                </span>
                <button
                  type="button"
                  className="btn btn-primary text-sm"
                  disabled={!goal.trim() || teamLoading}
                  onClick={handleExecute}
                >
                  {teamLoading ? '加载中...' : '开始执行'}
                </button>
              </div>
            </div>
            {teamError && (
              <div className="mt-3 rounded-lg border border-destructive/20 bg-destructive/5 p-3 text-sm text-destructive">
                {teamError}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Execution View ── */}
      {runState !== 'idle' && (
        <>
          {/* ── Agent Tabs — 匹配 session 侧边栏风格 ── */}
          <div className="flex border-b bg-card/50 px-2">
            {allTabs.map((tab) => {
              const isActive = activeTab === tab.key;
              const memberState = tab.key !== 'leader' ? memberStates.get(tab.key) : null;
              const dotColor = tab.role === 'leader'
                ? (runState === 'completed' ? 'bg-emerald-400' : runState === 'running' ? 'bg-primary animate-pulse' : 'bg-muted-foreground/30')
                : memberState?.status === 'done' ? 'bg-emerald-400' : memberState?.status === 'busy' ? 'bg-primary animate-pulse' : 'bg-muted-foreground/30';
              const roleLabel = tab.role === 'leader' ? 'Leader' : 'Member';
              return (
                <button
                  key={tab.key}
                  type="button"
                  className={`flex items-center gap-2 border-b-2 px-4 py-2.5 text-sm transition-colors ${
                    isActive
                      ? 'border-primary text-primary font-medium'
                      : 'border-transparent text-muted-foreground hover:text-foreground'
                  }`}
                  onClick={() => setActiveTab(tab.key)}
                >
                  <span className={`inline-block w-2 h-2 rounded-full shrink-0 ${dotColor}`} />
                  <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground/60 mr-1">
                    {roleLabel}
                  </span>
                  {tab.label}
                </button>
              );
            })}
          </div>

          {/* ── Log Area — 匹配 MessageList 风格 ── */}
          <div className="flex-1 overflow-y-auto px-4 py-6">
            <div className="mx-auto max-w-3xl space-y-0">
              {currentLogs.length === 0 && (
                <div className="py-20 text-center text-muted-foreground/50">
                  <p className="text-sm">等待执行开始...</p>
                  <p className="mt-1 text-xs">
                    {allTabs.find((t) => t.key === activeTab)?.label} 还没有输出信息
                  </p>
                </div>
              )}
              {currentLogs.map((entry) => (
                <LogBubble key={entry.id} entry={entry} />
              ))}
              <div ref={logsEndRef} />
            </div>
          </div>

          {/* ── Final Result — 可折叠，匹配消息气泡样式 ── */}
          {finalResult && (
            <div className="border-t border-border/50 bg-card/50">
              <button
                type="button"
                onClick={() => setFinalResultExpanded((v) => !v)}
                className="mx-auto flex w-full max-w-3xl items-center gap-2 px-4 py-2.5 text-left transition-colors hover:bg-muted/30"
                aria-expanded={finalResultExpanded}
              >
                <span className="inline-block w-2 h-2 rounded-full bg-emerald-400 shrink-0" />
                <span className="text-sm font-medium">🎉 最终结果</span>
                <span className="text-xs text-muted-foreground/60">
                  ({finalResult.length} 字符)
                </span>
                <svg
                  className={`ml-auto h-4 w-4 shrink-0 text-muted-foreground/40 transition-transform duration-200 ${
                    finalResultExpanded ? 'rotate-180' : ''
                  }`}
                  fill="none" stroke="currentColor" viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>
              {finalResultExpanded && (
                <div className="mx-auto max-w-3xl px-4 pb-4">
                  <div className="rounded-2xl border border-emerald-200/50 bg-card px-4 py-3">
                    <div className="markdown-content text-sm leading-relaxed">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {finalResult}
                      </ReactMarkdown>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
};
