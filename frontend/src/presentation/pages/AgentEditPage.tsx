/**
 * 表现层 - Agent 编辑/创建页
 */
import React, { useEffect, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAgentManagement } from '@application/services/useAgentManagement';
import { WizardContainer } from '@presentation/components/CreateAgentWizard/WizardContainer';
import { ConfigEditor } from '@presentation/components/ConfigEditor';
import {
  CONFIG_FILE_LABELS,
  CONFIG_FILE_DESCRIPTIONS,
} from '@domain/entities/agent';
import type { CreateAgentRequest } from '@domain/entities/agent';

const CONFIG_KEYS = [
  'identity_md',
  'soul_md',
  'agents_md',
  'bootstrap_md',
  'memory_md',
  'tools_md',
  'user_md',
] as const;

type ConfigKey = (typeof CONFIG_KEYS)[number];

export const AgentEditPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { currentAgent, isLoading, error, fetchAgent, createAgent, updateConfig } =
    useAgentManagement();

  const [activeTab, setActiveTab] = useState<ConfigKey>('identity_md');
  const [editValues, setEditValues] = useState<Record<ConfigKey, string>>({
    identity_md: '',
    soul_md: '',
    agents_md: '',
    bootstrap_md: '',
    memory_md: '',
    tools_md: '',
    user_md: '',
  });
  const [isDirty, setIsDirty] = useState(false);

  const isCreateMode = !id;

  // 编辑模式：加载 Agent 数据
  useEffect(() => {
    if (id) {
      fetchAgent(id);
    }
  }, [id, fetchAgent]);

  // 同步编辑值
  useEffect(() => {
    if (currentAgent) {
      setEditValues({
        identity_md: currentAgent.identity_md,
        soul_md: currentAgent.soul_md,
        agents_md: currentAgent.agents_md,
        bootstrap_md: currentAgent.bootstrap_md,
        memory_md: currentAgent.memory_md,
        tools_md: currentAgent.tools_md,
        user_md: currentAgent.user_md,
      });
      setIsDirty(false);
    }
  }, [currentAgent]);

  const handleConfigChange = useCallback(
    (key: ConfigKey, value: string) => {
      setEditValues((prev) => ({ ...prev, [key]: value }));
      setIsDirty(true);
    },
    []
  );

  const handleSave = async () => {
    if (!id || !isDirty) return;
    const result = await updateConfig(id, editValues);
    if (result) {
      setIsDirty(false);
    }
  };

  const handleCreate = async (data: CreateAgentRequest) => {
    const agent = await createAgent(data);
    if (agent) {
      navigate(`/agents/${agent.id}/edit`);
    }
  };

  // 创建模式：渲染向导
  if (isCreateMode) {
    return (
      <div className="h-screen bg-background">
        <WizardContainer
          onSubmit={handleCreate}
          onCancel={() => navigate('/agents')}
          isLoading={isLoading}
        />
      </div>
    );
  }

  // 编辑模式
  return (
    <div className="mx-auto max-w-6xl p-6">
      {/* 头部 */}
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => navigate('/agents')}
          >
            &larr; 返回
          </button>
          <div>
            <h1 className="text-xl font-bold">
              {currentAgent?.name ?? '加载中...'}
            </h1>
            {currentAgent?.description && (
              <p className="text-sm text-muted-foreground">
                {currentAgent.description}
              </p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {currentAgent && (
            <span className="text-xs text-muted-foreground">
              Config v{currentAgent.config_version}
            </span>
          )}
          <button
            type="button"
            className="btn btn-primary"
            onClick={handleSave}
            disabled={!isDirty || isLoading}
          >
            {isLoading ? '保存中...' : '保存'}
          </button>
        </div>
      </div>

      {/* 错误提示 */}
      {error && (
        <div className="mb-4 rounded-lg border border-destructive bg-destructive/10 p-3 text-sm text-destructive-foreground">
          {error}
        </div>
      )}

      {/* Tab 切换 */}
      <div className="mb-4 flex gap-1 overflow-x-auto border-b">
        {CONFIG_KEYS.map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => setActiveTab(key)}
            className={`whitespace-nowrap border-b-2 px-4 py-2.5 text-sm font-medium transition-colors ${
              activeTab === key
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            {CONFIG_FILE_LABELS[key]}
          </button>
        ))}
      </div>

      {/* 配置编辑器 */}
      <ConfigEditor
        key={activeTab}
        value={editValues[activeTab]}
        onChange={(v) => handleConfigChange(activeTab, v)}
        label={CONFIG_FILE_LABELS[activeTab]}
        description={CONFIG_FILE_DESCRIPTIONS[activeTab]}
      />

      {/* 未保存提示 */}
      {isDirty && (
        <div className="fixed bottom-4 right-4 rounded-lg border bg-card p-3 text-sm shadow-lg">
          有未保存的更改
        </div>
      )}
    </div>
  );
};
