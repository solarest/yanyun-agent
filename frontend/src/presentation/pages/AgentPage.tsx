/**
 * 表现层 - Agent 聊天页面（运行域）
 */
import React, { useState, useEffect } from 'react';
import { useTaskService } from '@application/services/useTaskService';
import { useAgentService } from '@application/services/useAgentService';
import { TaskList } from '@presentation/components/TaskList';
import { ChatInterface } from '@presentation/components/ChatInterface';
import type { Task } from '../../domain/entities/task';
import { llmConfigApi, type LLMProviderInfo } from '../../infrastructure/api/llmConfigApi';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export const AgentPage: React.FC = () => {
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [_llmProviders, setLlmProviders] = useState<LLMProviderInfo[]>([]);

  const {
    isLoading,
    error,
    tasks,
    currentTask,
    fetchTasks,
    setCurrentTask,
  } = useTaskService();

  const {
    isConnected,
    llmOutput,
    currentPhase,
    toolCalls,
    connect,
    disconnect,
  } = useAgentService(API_BASE_URL);

  // 加载任务列表
  useEffect(() => {
    fetchTasks();
  }, [fetchTasks]);

  // 加载 LLM 配置
  useEffect(() => {
    const loadLlmProviders = async () => {
      try {
        const providers = await llmConfigApi.getProviders();
        setLlmProviders(providers);
      } catch (err) {
        console.error('加载 LLM 配置失败:', err);
        setLlmProviders([
          { name: 'openai', availableModels: ['gpt-4', 'gpt-3.5-turbo'] },
          { name: 'anthropic', availableModels: ['claude-3-opus', 'claude-3-sonnet'] },
        ]);
      }
    };
    loadLlmProviders();
  }, []);

  // 当创建任务后，连接到 SSE
  useEffect(() => {
    if (currentTask && currentTask.status === 'running') {
      connect(currentTask.id);
      setSelectedTask(currentTask);
    }
  }, [currentTask, connect]);

  // 选择任务
  const handleSelectTask = (task: Task) => {
    setSelectedTask(task);
    setCurrentTask(task);
    if (task.status === 'running') {
      connect(task.id);
    } else {
      disconnect();
    }
  };

  return (
    <div className="flex h-screen bg-background">
      {/* 侧边栏 */}
      <div
        className={`border-r bg-card transition-all ${
          sidebarOpen ? 'w-80' : 'w-0 overflow-hidden'
        }`}
      >
        <div className="flex h-full flex-col">
          {/* 侧边栏头部 */}
          <div className="border-b p-4">
            <h1 className="mb-3 text-lg font-semibold">Agent 任务</h1>
          </div>

          {/* 任务列表 */}
          <div className="flex-1 overflow-y-auto p-4">
            <TaskList
              tasks={tasks}
              selectedTaskId={selectedTask?.id || null}
              onSelectTask={handleSelectTask}
              isLoading={isLoading}
            />
          </div>
        </div>
      </div>

      {/* 主内容区 */}
      <div className="flex flex-1 flex-col">
        {/* 顶部栏 */}
        <div className="flex items-center gap-2 border-b px-4 py-3">
          <button
            className="btn btn-ghost"
            onClick={() => setSidebarOpen(!sidebarOpen)}
          >
            {sidebarOpen ? '◀' : '▶'}
          </button>
          {selectedTask && (
            <div>
              <h2 className="font-medium">{selectedTask.agentName}</h2>
              <p className="text-xs text-muted-foreground">
                {selectedTask.userInput}
              </p>
            </div>
          )}
        </div>

        {/* 聊天区域 */}
        <div className="flex-1">
          {selectedTask ? (
            <ChatInterface
              llmOutput={llmOutput}
              toolCalls={toolCalls}
              currentPhase={currentPhase}
              isConnected={isConnected}
              taskStatus={selectedTask.status}
            />
          ) : (
            <div className="flex h-full items-center justify-center">
              <div className="text-center">
                <div className="text-2xl font-medium text-muted-foreground">
                  欢迎使用 Agent
                </div>
                <div className="mt-2 text-sm text-muted-foreground">
                  选择一个任务查看对话
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 错误提示 */}
      {error && (
        <div className="fixed bottom-4 right-4 rounded-lg border border-destructive bg-destructive/10 p-4 text-sm text-destructive-foreground">
          {error}
        </div>
      )}
    </div>
  );
};
