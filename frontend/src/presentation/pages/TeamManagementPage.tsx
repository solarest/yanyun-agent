/**
 * 表现层 - Team 管理列表页
 */
import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTeamManagement } from '@application/services/useTeamManagement';
import type { Team } from '@domain/entities/team';

/** 头像颜色生成 */
function getAvatarColor(name: string): string {
  const colors = [
    '#6366f1', '#8b5cf6', '#ec4899', '#f43f5e',
    '#f97316', '#eab308', '#22c55e', '#06b6d4',
  ];
  const hash = name.split('').reduce((a, c) => a + c.charCodeAt(0), 0);
  return colors[hash % colors.length];
}

const STATUS_LABELS: Record<string, string> = {
  idle: '空闲',
  planning: '规划中',
  executing: '执行中',
  completed: '已完成',
  failed: '失败',
};

const STATUS_COLORS: Record<string, string> = {
  idle: 'bg-gray-100 text-gray-600',
  planning: 'bg-blue-100 text-blue-700',
  executing: 'bg-yellow-100 text-yellow-700',
  completed: 'bg-green-100 text-green-700',
  failed: 'bg-red-100 text-red-700',
};

export const TeamManagementPage: React.FC = () => {
  const { teams, isLoading, error, fetchTeams, deleteTeam } = useTeamManagement();
  const [deleteTarget, setDeleteTarget] = useState<Team | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  useEffect(() => {
    fetchTeams();
  }, [fetchTeams]);

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setIsDeleting(true);
    const success = await deleteTeam(deleteTarget.id);
    if (success) setDeleteTarget(null);
    setIsDeleting(false);
  };

  return (
    <div className="mx-auto max-w-6xl p-6">
      {/* 头部 */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">团队管理</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            创建和管理多 Agent 协作团队
          </p>
        </div>
        {teams.length > 0 && (
          <Link to="/teams/new" className="btn btn-primary">
            + 新建团队
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
      {isLoading && teams.length === 0 && (
        <div className="flex items-center justify-center py-20">
          <p className="text-muted-foreground">加载中...</p>
        </div>
      )}

      {/* 空状态 */}
      {!isLoading && teams.length === 0 && (
        <div className="flex flex-col items-center justify-center py-20">
          <p className="mb-4 text-lg text-muted-foreground">暂无团队</p>
          <Link to="/teams/new" className="btn btn-primary">
            创建第一个团队
          </Link>
        </div>
      )}

      {/* Team 卡片网格 */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {teams.map((team) => (
          <div
            key={team.id}
            className="group rounded-xl border bg-card p-5 transition-shadow hover:shadow-md"
          >
            <div className="mb-3 flex items-start gap-3">
              <div
                className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full text-lg font-bold text-white"
                style={{ backgroundColor: getAvatarColor(team.name) }}
              >
                {team.name.charAt(0).toUpperCase()}
              </div>
              <div className="min-w-0 flex-1">
                <h3 className="truncate font-semibold">{team.name}</h3>
                {team.description && (
                  <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">
                    {team.description}
                  </p>
                )}
              </div>
            </div>

            {/* 状态与成员数 */}
            <div className="mb-3 flex items-center gap-2">
              <span
                className={`rounded-full px-2 py-0.5 text-xs ${STATUS_COLORS[team.status] ?? 'bg-gray-100 text-gray-600'}`}
              >
                {STATUS_LABELS[team.status] ?? team.status}
              </span>
              <span className="text-xs text-muted-foreground">
                {team.member_count} 名成员
              </span>
            </div>

            {/* 操作按钮 */}
            <div className="flex items-center justify-between border-t pt-3">
              <Link
                to={`/teams/${team.id}`}
                className="btn btn-primary px-3 py-1 text-xs"
              >
                查看
              </Link>
              <div className="flex gap-2">
                <Link
                  to={`/teams/${team.id}/execute`}
                  className="btn btn-outline px-3 py-1 text-xs"
                >
                  执行
                </Link>
                <button
                  type="button"
                  className="btn btn-outline px-3 py-1 text-xs text-destructive hover:bg-destructive/10"
                  onClick={() => setDeleteTarget(team)}
                >
                  删除
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* 删除确认对话框 */}
      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-sm rounded-xl bg-background p-6 shadow-lg">
            <h3 className="text-lg font-semibold">确认删除</h3>
            <p className="mt-2 text-sm text-muted-foreground">
              确定要删除团队「{deleteTarget.name}」吗？此操作不可撤销。
            </p>
            <div className="mt-4 flex justify-end gap-3">
              <button
                type="button"
                className="btn btn-outline px-4 py-2 text-sm"
                onClick={() => setDeleteTarget(null)}
                disabled={isDeleting}
              >
                取消
              </button>
              <button
                type="button"
                className="btn bg-destructive px-4 py-2 text-sm text-white"
                onClick={handleDelete}
                disabled={isDeleting}
              >
                {isDeleting ? '删除中...' : '删除'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
