/**
 * 表现层 - 任务列表组件
 */
import React from 'react';
import type { Task } from '../../domain/entities/task';

interface TaskListProps {
  tasks: Task[];
  selectedTaskId: string | null;
  onSelectTask: (task: Task) => void;
  isLoading: boolean;
}

const statusColors: Record<string, string> = {
  pending: 'bg-warning text-warning-foreground',
  running: 'bg-primary text-primary-foreground',
  completed: 'bg-success text-success-foreground',
  failed: 'bg-destructive text-destructive-foreground',
  cancelled: 'bg-muted text-muted-foreground',
};

const statusLabels: Record<string, string> = {
  pending: '等待中',
  running: '运行中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
};

export const TaskList: React.FC<TaskListProps> = ({
  tasks,
  selectedTaskId,
  onSelectTask,
  isLoading,
}) => {
  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="text-sm text-muted-foreground">加载中...</div>
      </div>
    );
  }

  if (tasks.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-8">
        <div className="text-sm text-muted-foreground">暂无任务</div>
        <div className="mt-1 text-xs text-muted-foreground">
          点击"创建 Agent"开始
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {tasks.map((task) => (
        <button
          key={task.id}
          className={`w-full rounded-md border p-3 text-left transition-colors hover:bg-accent ${
            selectedTaskId === task.id
              ? 'border-primary bg-accent'
              : 'border-transparent'
          }`}
          onClick={() => onSelectTask(task)}
        >
          <div className="mb-1 flex items-center justify-between">
            <span className="truncate text-sm font-medium">
              {task.agentName}
            </span>
            <span
              className={`ml-2 rounded-full px-2 py-0.5 text-xs ${
                statusColors[task.status] || 'bg-muted text-muted-foreground'
              }`}
            >
              {statusLabels[task.status] || task.status}
            </span>
          </div>
          <div className="truncate text-xs text-muted-foreground">
            {task.userInput}
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            {new Date(task.createdAt).toLocaleString('zh-CN')}
          </div>
        </button>
      ))}
    </div>
  );
};
