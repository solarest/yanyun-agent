/**
 * 表现层 - 创建 Agent 对话框组件
 */
import React, { useState, useEffect } from 'react';
import { LLMProviderInfo } from '../../infrastructure/api/llmConfigApi';

interface CreateAgentDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: {
    agentName: string;
    userInput: string;
    systemPrompt: string;
    provider: string;
    model: string;
  }) => void;
  isLoading: boolean;
  llmProviders: LLMProviderInfo[];
}

export const CreateAgentDialog: React.FC<CreateAgentDialogProps> = ({
  isOpen,
  onClose,
  onSubmit,
  isLoading,
  llmProviders,
}) => {
  const [agentName, setAgentName] = useState('');
  const [userInput, setUserInput] = useState('');
  const [systemPrompt, setSystemPrompt] = useState('You are a helpful coding assistant.');
  const [provider, setProvider] = useState(llmProviders[0]?.name || '');
  const [model, setModel] = useState(llmProviders[0]?.availableModels[0] || '');

  // 当提供商改变时，重置模型为该提供商的第一个可用模型
  useEffect(() => {
    const selectedProvider = llmProviders.find(p => p.name === provider);
    if (selectedProvider && selectedProvider.availableModels.length > 0) {
      setModel(selectedProvider.availableModels[0]);
    }
  }, [provider, llmProviders]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({ agentName, userInput, systemPrompt, provider, model });
    // 重置表单
    setAgentName('');
    setUserInput('');
    setSystemPrompt('You are a helpful coding assistant.');
    setProvider(llmProviders[0]?.name || '');
    setModel(llmProviders[0]?.availableModels[0] || '');
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-2xl rounded-lg border bg-card p-6 shadow-lg">
        <h2 className="mb-4 text-xl font-semibold">创建 Agent</h2>
        
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Agent 名称 */}
          <div>
            <label className="mb-1 block text-sm font-medium">
              Agent 名称
            </label>
            <input
              type="text"
              className="input"
              value={agentName}
              onChange={(e) => setAgentName(e.target.value)}
              placeholder="例如：Code Assistant"
              required
            />
          </div>

          {/* 用户输入 */}
          <div>
            <label className="mb-1 block text-sm font-medium">
              任务描述
            </label>
            <textarea
              className="textarea min-h-[120px]"
              value={userInput}
              onChange={(e) => setUserInput(e.target.value)}
              placeholder="描述你希望 Agent 完成的任务..."
              required
            />
          </div>

          {/* 系统提示词 */}
          <div>
            <label className="mb-1 block text-sm font-medium">
              系统提示词
            </label>
            <textarea
              className="textarea min-h-[80px]"
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              placeholder="定义 Agent 的行为和角色..."
            />
          </div>

          {/* 提供商选择 */}
          <div>
            <label className="mb-1 block text-sm font-medium">
              LLM 提供商
            </label>
            <select
              className="input"
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
            >
              {llmProviders.map(p => (
                <option key={p.name} value={p.name}>
                  {p.name.toUpperCase()}
                </option>
              ))}
            </select>
          </div>

          {/* 模型选择 */}
          <div>
            <label className="mb-1 block text-sm font-medium">
              模型
            </label>
            <select
              className="input"
              value={model}
              onChange={(e) => setModel(e.target.value)}
            >
              {llmProviders
                .find(p => p.name === provider)
                ?.availableModels.map(m => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
            </select>
          </div>

          {/* 按钮 */}
          <div className="flex justify-end gap-2 pt-4">
            <button
              type="button"
              className="btn btn-outline"
              onClick={onClose}
              disabled={isLoading}
            >
              取消
            </button>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={isLoading}
            >
              {isLoading ? '创建中...' : '创建并开始'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
