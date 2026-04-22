/**
 * 表现层 - 创建 Agent 对话框组件
 */
import React, { useState } from 'react';

interface CreateAgentDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: {
    agentName: string;
    userInput: string;
    systemPrompt: string;
    model: string;
  }) => void;
  isLoading: boolean;
}

const MODELS = [
  { value: 'gpt-4', label: 'GPT-4' },
  { value: 'gpt-3.5-turbo', label: 'GPT-3.5 Turbo' },
  { value: 'claude-3-opus', label: 'Claude 3 Opus' },
  { value: 'claude-3-sonnet', label: 'Claude 3 Sonnet' },
];

export const CreateAgentDialog: React.FC<CreateAgentDialogProps> = ({
  isOpen,
  onClose,
  onSubmit,
  isLoading,
}) => {
  const [agentName, setAgentName] = useState('');
  const [userInput, setUserInput] = useState('');
  const [systemPrompt, setSystemPrompt] = useState('You are a helpful coding assistant.');
  const [model, setModel] = useState('gpt-4');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({ agentName, userInput, systemPrompt, model });
    // 重置表单
    setAgentName('');
    setUserInput('');
    setSystemPrompt('You are a helpful coding assistant.');
    setModel('gpt-4');
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
              {MODELS.map(m => (
                <option key={m.value} value={m.value}>
                  {m.label}
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
