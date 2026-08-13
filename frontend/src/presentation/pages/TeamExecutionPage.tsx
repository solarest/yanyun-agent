/**
 * 表现层 - Team 执行页
 *
 * 仅负责布局编排；执行/流式/恢复逻辑在 useTeamExecution，
 * 时间线渲染在 @presentation/components/team/TeamTimeline。
 */
import React from 'react';
import { useParams, Link } from 'react-router-dom';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useTeamExecution } from '@application/services/useTeamExecution';
import {
  TeamTimeline,
  StatusBadge,
} from '@presentation/components/team/TeamTimeline';
import { WorkspaceSidebar } from '@presentation/components/team/WorkspaceSidebar';
import { GoalComposer } from '@presentation/components/team/GoalComposer';
import { FollowUpComposer } from '@presentation/components/team/FollowUpComposer';

export const TeamExecutionPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();

  const {
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
  } = useTeamExecution(id || '');

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
        <GoalComposer
          value={goal}
          onChange={setGoal}
          onSubmit={handleExecute}
          disabled={teamLoading}
          buttonLabel={teamLoading ? '加载中...' : '开始执行'}
          error={teamError}
        />
      )}

      {runState !== 'idle' && (
        <>
          {/* Tab 条 */}
          <div className="flex border-b bg-card/50 px-2">
            {allTabs.map((tab) => {
              const isActive = activeTab === tab.key;
              const memberState = tab.key !== 'leader' ? memberStates.get(tab.key) : null;
              const dotColor = tab.role === 'leader'
                ? (runState === 'completed' ? 'bg-emerald-400' : runState === 'running' ? 'bg-primary animate-pulse' : 'bg-muted-foreground/30')
                : memberState?.status === 'done' ? 'bg-emerald-400' : memberState?.status === 'busy' ? 'bg-primary animate-pulse' : 'bg-muted-foreground/30';
              return (
                <button
                  key={tab.key}
                  type="button"
                  className={`flex items-center gap-2 border-b-2 px-4 py-2.5 text-sm transition-colors ${isActive ? 'border-primary text-primary font-medium' : 'border-transparent text-muted-foreground hover:text-foreground'}`}
                  onClick={() => setActiveTab(tab.key)}
                >
                  <span className={`inline-block w-2 h-2 rounded-full shrink-0 ${dotColor}`} />
                  {tab.label}
                </button>
              );
            })}
            <button
              type="button"
              onClick={() => setSidebarOpen((v) => !v)}
              className="ml-auto flex items-center gap-1.5 border-b-2 border-transparent px-4 py-2.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              <span className="text-xs">文件</span>
              {workspaceFiles.length > 0 && <span className="rounded-full bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">{workspaceFiles.length}</span>}
              <svg className={`h-3.5 w-3.5 transition-transform duration-200 ${sidebarOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
            </button>
          </div>

          <div className="flex flex-1 overflow-hidden">
            <div className="flex flex-1 flex-col overflow-hidden">
              <div ref={scrollContainerRef} className="flex-1 overflow-y-scroll px-4 py-6">
                <div className="mx-auto max-w-3xl">
                  {timelineItems.length === 0 && !showStreaming && (
                    <div className="py-20 text-center text-muted-foreground/50"><p className="text-sm">等待执行开始...</p></div>
                  )}
                  <TeamTimeline
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
              <WorkspaceSidebar files={workspaceFiles} onRefresh={fetchWorkspaceFiles} />
            )}
          </div>

          <FollowUpComposer
            value={followUpInput}
            onChange={handleFollowUpInputChange}
            onSubmit={() => handleFollowUp()}
            disabled={isFollowUpRunning || runState === 'running'}
            runningLabel={isFollowUpRunning ? '执行中...' : '发送'}
          />
        </>
      )}
    </div>
  );
};
