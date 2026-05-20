/**
 * 表现层 - Agent 管理列表页
 */
import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAgentManagement } from '@application/services/useAgentManagement';
import { DeleteAgentDialog } from '@presentation/components/DeleteAgentDialog';
import { VIBE_LABELS } from '@application/services/useAgentGenerator';
import type { Agent } from '@domain/entities/agent';

/** 头像颜色生成 */
function getAvatarColor(name: string): string {
  const colors = [
    '#6366f1', '#8b5cf6', '#ec4899', '#f43f5e',
    '#f97316', '#eab308', '#22c55e', '#06b6d4',
    '#3b82f6', '#a855f7', '#14b8a6', '#f59e0b',
  ];
  const hash = name.split('').reduce((a, c) => a + c.charCodeAt(0), 0);
  return colors[hash % colors.length];
}

export const AgentManagementPage: React.FC = () => {
  const { agents, isLoading, error, fetchAgents, deleteAgent } =
    useAgentManagement();
  const [deleteTarget, setDeleteTarget] = useState<Agent | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  useEffect(() => {
    fetchAgents();
  }, [fetchAgents]);

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setIsDeleting(true);
    const success = await deleteAgent(deleteTarget.id);
    if (success) {
      setDeleteTarget(null);
    }
    setIsDeleting(false);
  };

  return (
    <div className="mx-auto max-w-6xl p-6">
      {/* 头部 */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Agent 管理</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            管理你的 AI Agent 及其配置
          </p>
        </div>
        {agents.length > 0 && (
          <Link to="/agents/new" className="btn btn-primary">
            + 新建 Agent
          </Link>
        )}
      </div>

      {/* 错误提示 */}
      {error && (
        <div className="mb-4 rounded-lg border border-destructive bg-destructive/10 p-3 text-sm text-destructive-foreground">
          {error}
        </div>
      )}

      {/* 加载状态 */}
      {isLoading && agents.length === 0 && (
        <div className="flex items-center justify-center py-20">
          <p className="text-muted-foreground">加载中...</p>
        </div>
      )}

      {/* 空状态 */}
      {!isLoading && agents.length === 0 && (
        <div className="flex flex-col items-center justify-center py-20">
          <p className="mb-4 text-lg text-muted-foreground">
            暂无 Agent
          </p>
          <Link to="/agents/new" className="btn btn-primary">
            创建第一个 Agent
          </Link>
        </div>
      )}

      {/* Agent 卡片网格 */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {agents.map((agent) => (
          <div
            key={agent.id}
            className="group rounded-xl border bg-card p-5 transition-shadow hover:shadow-md"
          >
            <div className="mb-3 flex items-start gap-3">
              {/* 头像 */}
              <div
                className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full text-lg font-bold text-white"
                style={{
                  backgroundColor: getAvatarColor(agent.name),
                }}
              >
                {agent.name.charAt(0).toUpperCase()}
              </div>
              <div className="min-w-0 flex-1">
                <h3 className="truncate font-semibold">{agent.name}</h3>
                {agent.description && (
                  <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">
                    {agent.description}
                  </p>
                )}
              </div>
            </div>

            {/* Vibes */}
            {agent.vibes.length > 0 && (
              <div className="mb-3 flex flex-wrap gap-1">
                {agent.vibes.map((v) => (
                  <span
                    key={v}
                    className="rounded-full bg-primary/10 px-2 py-0.5 text-xs text-primary"
                  >
                    {VIBE_LABELS[v] ?? v}
                  </span>
                ))}
              </div>
            )}

            {/* 操作按钮 */}
            <div className="flex items-center justify-between border-t pt-3">
              <span className="text-xs text-muted-foreground">
                v{agent.config_version}
              </span>
              <div className="flex gap-2">
                <Link
                  to={`/agents/${agent.id}/chat`}
                  className="btn btn-primary px-3 py-1 text-xs"
                >
                  对话
                </Link>
                <Link
                  to={`/agents/${agent.id}/edit`}
                  className="btn btn-outline px-3 py-1 text-xs"
                >
                  编辑
                </Link>
                <button
                  type="button"
                  className="btn btn-outline px-3 py-1 text-xs text-destructive hover:bg-destructive/10"
                  onClick={() => setDeleteTarget(agent)}
                >
                  删除
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* 删除确认对话框 */}
      <DeleteAgentDialog
        isOpen={deleteTarget !== null}
        agentName={deleteTarget?.name ?? ''}
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
        isLoading={isDeleting}
      />
    </div>
  );
};
