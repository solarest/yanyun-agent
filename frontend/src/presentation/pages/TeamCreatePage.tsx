/**
 * 表现层 - Team 创建页
 *
 * 向导步骤：
 * 1. 选择 Leader（从已有 Agent 中选择）
 * 2. 选择 Members（多选，排除已选的 Leader）
 * 3. 填写名称与描述
 */
import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTeamManagement } from '@application/services/useTeamManagement';
import { useAgentManagement } from '@application/services/useAgentManagement';

export const TeamCreatePage: React.FC = () => {
  const navigate = useNavigate();
  const { createTeam, isLoading: isCreating, error } = useTeamManagement();
  const { agents, fetchAgents, isLoading: isAgentsLoading } = useAgentManagement();

  const [step, setStep] = useState(1);
  const [leaderId, setLeaderId] = useState<string>('');
  const [memberIds, setMemberIds] = useState<string[]>([]);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');

  useEffect(() => {
    fetchAgents();
  }, [fetchAgents]);

  const toggleMember = (agentId: string) => {
    setMemberIds((prev) =>
      prev.includes(agentId)
        ? prev.filter((id) => id !== agentId)
        : [...prev, agentId]
    );
  };

  const handleSubmit = async () => {
    const result = await createTeam({
      name,
      description,
      leader_id: leaderId,
      member_ids: memberIds,
    });
    if (result) {
      navigate('/teams');
    }
  };

  const availableMembers = agents.filter((a) => a.id !== leaderId);
  const leaderAgent = agents.find((a) => a.id === leaderId);

  return (
    <div className="mx-auto max-w-2xl p-6">
      <h1 className="mb-6 text-2xl font-bold">创建团队</h1>

      {/* 步骤指示器 */}
      <div className="mb-8 flex items-center gap-4">
        {[1, 2, 3].map((s) => (
          <React.Fragment key={s}>
            <div
              className={`flex h-8 w-8 items-center justify-center rounded-full text-sm font-bold ${
                s <= step
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted text-muted-foreground'
              }`}
            >
              {s}
            </div>
            {s < 3 && <div className="h-0.5 flex-1 bg-muted" />}
          </React.Fragment>
        ))}
      </div>

      {/* 错误提示 */}
      {error && (
        <div className="mb-4 rounded-lg border border-destructive bg-destructive/10 p-3 text-sm">
          {error}
        </div>
      )}

      {/* 步骤 1: 选择 Leader */}
      {step === 1 && (
        <div>
          <h2 className="mb-4 text-lg font-semibold">选择团队 Leader</h2>
          <p className="mb-4 text-sm text-muted-foreground">
            Leader 负责分析需求、拆解任务、分配给成员并评估结果。
          </p>
          {isAgentsLoading ? (
            <p className="text-muted-foreground">加载 Agent 列表...</p>
          ) : agents.length === 0 ? (
            <p className="text-muted-foreground">
              暂无可用 Agent，请先
              <button
                className="text-primary underline"
                onClick={() => navigate('/agents/new')}
              >
                创建 Agent
              </button>
            </p>
          ) : (
            <div className="space-y-2">
              {agents.map((agent) => (
                <button
                  key={agent.id}
                  type="button"
                  className={`w-full rounded-lg border p-4 text-left transition-colors ${
                    leaderId === agent.id
                      ? 'border-primary bg-primary/5'
                      : 'border-border hover:bg-secondary/50'
                  }`}
                  onClick={() => setLeaderId(agent.id)}
                >
                  <p className="font-medium">{agent.name}</p>
                  {agent.description && (
                    <p className="mt-1 text-xs text-muted-foreground">
                      {agent.description}
                    </p>
                  )}
                </button>
              ))}
            </div>
          )}
          <div className="mt-6 flex justify-end">
            <button
              type="button"
              className="btn btn-primary"
              disabled={!leaderId}
              onClick={() => setStep(2)}
            >
              下一步
            </button>
          </div>
        </div>
      )}

      {/* 步骤 2: 选择 Members */}
      {step === 2 && (
        <div>
          <h2 className="mb-4 text-lg font-semibold">选择团队成员</h2>
          <p className="mb-4 text-sm text-muted-foreground">
            Members 负责接受 Leader 的任务并执行。选中的 Leader：<strong>{leaderAgent?.name}</strong>
          </p>
          {availableMembers.length === 0 ? (
            <p className="text-muted-foreground">没有其他可用 Agent</p>
          ) : (
            <div className="space-y-2">
              {availableMembers.map((agent) => (
                <button
                  key={agent.id}
                  type="button"
                  className={`w-full rounded-lg border p-4 text-left transition-colors ${
                    memberIds.includes(agent.id)
                      ? 'border-primary bg-primary/5'
                      : 'border-border hover:bg-secondary/50'
                  }`}
                  onClick={() => toggleMember(agent.id)}
                >
                  <div className="flex items-center gap-3">
                    <input
                      type="checkbox"
                      checked={memberIds.includes(agent.id)}
                      readOnly
                      className="h-4 w-4"
                    />
                    <div>
                      <p className="font-medium">{agent.name}</p>
                      {agent.description && (
                        <p className="mt-1 text-xs text-muted-foreground">
                          {agent.description}
                        </p>
                      )}
                    </div>
                  </div>
                </button>
              ))}
            </div>
          )}
          <div className="mt-6 flex justify-between">
            <button
              type="button"
              className="btn btn-outline"
              onClick={() => setStep(1)}
            >
              上一步
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={memberIds.length === 0}
              onClick={() => setStep(3)}
            >
              下一步
            </button>
          </div>
        </div>
      )}

      {/* 步骤 3: 名称与描述 */}
      {step === 3 && (
        <div>
          <h2 className="mb-4 text-lg font-semibold">团队信息</h2>

          {/* 摘要 */}
          <div className="mb-4 rounded-lg bg-secondary/30 p-3 text-sm">
            <p>
              <strong>Leader:</strong> {leaderAgent?.name}
            </p>
            <p>
              <strong>Members:</strong>{' '}
              {memberIds
                .map((id) => agents.find((a) => a.id === id)?.name)
                .filter(Boolean)
                .join(', ') || '无'}
            </p>
          </div>

          <div className="space-y-4">
            <div>
              <label className="mb-1.5 block text-sm font-medium">团队名称</label>
              <input
                type="text"
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                placeholder="例如：内容创作团队"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium">团队描述</label>
              <textarea
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
                rows={3}
                placeholder="描述团队的功能和目标..."
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>
          </div>

          <div className="mt-6 flex justify-between">
            <button
              type="button"
              className="btn btn-outline"
              onClick={() => setStep(2)}
            >
              上一步
            </button>
            <button
              type="button"
              className="btn btn-primary"
              disabled={!name.trim() || isCreating}
              onClick={handleSubmit}
            >
              {isCreating ? '创建中...' : '创建团队'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
