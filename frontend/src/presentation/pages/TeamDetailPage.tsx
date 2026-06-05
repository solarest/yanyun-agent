/**
 * 表现层 - Team 详情页
 *
 * 显示团队信息、成员列表，提供执行入口。
 */
import React, { useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useTeamManagement } from '@application/services/useTeamManagement';

export const TeamDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const { currentTeam, fetchTeam, isLoading, error } = useTeamManagement();

  useEffect(() => {
    if (id) fetchTeam(id);
  }, [id, fetchTeam]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <p className="text-muted-foreground">加载中...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="mx-auto max-w-4xl p-6">
        <div className="rounded-lg border border-destructive bg-destructive/10 p-4 text-sm">
          {error}
        </div>
      </div>
    );
  }

  if (!currentTeam) {
    return (
      <div className="flex items-center justify-center py-20">
        <p className="text-muted-foreground">团队未找到</p>
      </div>
    );
  }

  const leader = currentTeam.members?.find((m) => m.role === 'leader');
  const members = currentTeam.members?.filter((m) => m.role === 'member') ?? [];

  const STATUS_LABELS: Record<string, string> = {
    idle: '空闲', planning: '规划中', executing: '执行中', completed: '已完成', failed: '失败',
  };

  return (
    <div className="mx-auto max-w-4xl p-6">
      {/* 头部 */}
      <div className="mb-6">
        <Link to="/teams" className="text-sm text-muted-foreground hover:text-foreground">
          ← 返回团队列表
        </Link>
        <div className="mt-3 flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold">{currentTeam.name}</h1>
            {currentTeam.description && (
              <p className="mt-1 text-sm text-muted-foreground">{currentTeam.description}</p>
            )}
          </div>
          <Link
            to={`/teams/${currentTeam.id}/execute`}
            className="btn btn-primary"
          >
            执行任务
          </Link>
        </div>
        <div className="mt-2 flex items-center gap-3 text-sm text-muted-foreground">
          <span>状态: {STATUS_LABELS[currentTeam.status] ?? currentTeam.status}</span>
          <span>成员: {currentTeam.member_count} 人</span>
        </div>
      </div>

      {/* 成员列表 */}
      <div className="mb-6">
        <h2 className="mb-3 text-lg font-semibold">团队成员</h2>

        {/* Leader */}
        {leader && (
          <div className="mb-3 rounded-lg border border-primary/30 bg-primary/5 p-4">
            <div className="flex items-center gap-3">
              <span className="rounded-full bg-primary/20 px-2 py-0.5 text-xs font-medium text-primary">
                Leader
              </span>
              <span className="font-medium">{leader.agent_name || leader.agent_id}</span>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              负责分析需求、拆解任务、分配给成员、评估结果
            </p>
          </div>
        )}

        {/* Members */}
        {members.map((member) => (
          <div key={member.id} className="mb-2 rounded-lg border p-4">
            <div className="flex items-center gap-3">
              <span className="rounded-full bg-secondary px-2 py-0.5 text-xs font-medium">
                Member
              </span>
              <span className="font-medium">{member.agent_name || member.agent_id}</span>
              <span className="text-xs text-muted-foreground">
                ({member.status})
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* 当前目标 */}
      {currentTeam.goal && (
        <div className="rounded-lg bg-secondary/30 p-4">
          <h3 className="text-sm font-semibold">当前目标</h3>
          <p className="mt-1 text-sm">{currentTeam.goal}</p>
        </div>
      )}
    </div>
  );
};
