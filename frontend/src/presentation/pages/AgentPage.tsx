/**
 * 表现层 - Agent 主页面
 */
import React, { useState, useEffect } from 'react';
import { useTaskService } from '@application/services/useTaskService';
import { useAgentService } from '@application/services/useAgentService';
import { CreateAgentDialog } from '@presentation/components/CreateAgentDialog';
import { TaskList } from '@presentation/components/TaskList';
import { ChatInterface } from '@presentation/components/ChatInterface';
import type { Task } from '../../domain/entities/task';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export const AgentPage: React.FC = () => {
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const {
    isLoading,
    error,
    tasks,
    currentTask,
    createTask,
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

  // 创建 Agent
  const handleCreateAgent = async (data: {
    agentName: string;
    userInput: string;
    systemPrompt: string;
    model: string;
  }) => {
    try {
      await createTask({
        agentName: data.agentName,
        userInput: data.userInput,
        config: {
          systemPrompt: data.systemPrompt,
          model: data.model,
        },
      });
      setShowCreateDialog(false);
    } catch (err) {
      console.error('创建任务失败:', err);
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
            <button
              className="btn btn-primary w-full"
              onClick={() => setShowCreateDialog(true)}
              disabled={isLoading}
            >
              创建 Agent
            </button>
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
                  点击左侧"创建 Agent"开始对话
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

      {/* 创建 Agent 对话框 */}
      <CreateAgentDialog
        isOpen={showCreateDialog}
        onClose={() => setShowCreateDialog(false)}
        onSubmit={handleCreateAgent}
        isLoading={isLoading}
      />
    </div>
  );
};
