/**
 * 表现层 - 任务列表面板
 * 
 * 显示在输入框上方，展示当前任务的步骤列表。
 * 只在有任务时显示，无任务时返回 null。
 */
import React from 'react';
import type { TaskProgress, TaskStepStatus } from '@application/services/useChat';

interface TaskPanelProps {
  task: TaskProgress | null;
}

const STEP_STATUS_ICONS: Record<TaskStepStatus, string> = {
  pending: '○',
  running: '◉',
  completed: '✓',
  failed: '✗',
};

export const TaskPanel: React.FC<TaskPanelProps> = ({ task }) => {
  // 无任务或无步骤时不显示
  if (!task?.steps.length) return null;

  return (
    <div className="border-t bg-muted/30 px-4 py-3">
      <div className="mx-auto max-w-3xl">
        <div className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          当前任务列表
        </div>
        <ul className="space-y-1.5">
          {task.steps.map((step) => (
            <li
              key={step.id}
              className="flex items-start gap-2 text-sm text-foreground"
            >
              <span className="mt-0.5 text-muted-foreground">
                {STEP_STATUS_ICONS[step.status]}
              </span>
              <span className="flex-1">
                <span className="font-medium">Task {step.id}</span>
                <span className="text-muted-foreground">: {step.description}</span>
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
};
