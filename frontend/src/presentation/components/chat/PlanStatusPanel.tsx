/**
 * 表现层 - Plan 常驻状态栏
 */
import React from 'react';
import type {
  PlanProgress,
  PlanStatus,
  PlanStepStatus,
} from '@application/services/useChat';

interface PlanStatusPanelProps {
  plan: PlanProgress | null;
}

const STATUS_LABELS: Record<PlanStatus, string> = {
  planning: 'Planning',
  executing: 'Running',
  completed: 'Done',
  failed: 'Failed',
};

const STEP_STATUS_LABELS: Record<PlanStepStatus, string> = {
  pending: 'Pending',
  running: 'Running',
  completed: 'Done',
  failed: 'Failed',
};

const stepDotClass = (status: PlanStepStatus): string => {
  if (status === 'completed') return 'bg-success';
  if (status === 'failed') return 'bg-destructive';
  if (status === 'running') return 'animate-pulse bg-primary';
  return 'bg-muted-foreground/40';
};

const statusBadgeClass = (status: PlanStatus): string => {
  if (status === 'completed') return 'border-success/30 bg-success/10 text-success';
  if (status === 'failed') return 'border-destructive/30 bg-destructive/10 text-destructive';
  if (status === 'executing') return 'border-primary/20 bg-primary/10 text-primary';
  return 'border-border bg-muted text-muted-foreground';
};

export const PlanStatusPanel: React.FC<PlanStatusPanelProps> = ({ plan }) => {
  if (!plan) return null;

  return (
    <div className="border-b bg-card/70 px-4 py-3">
      <div className="mx-auto max-w-3xl">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="min-w-0">
            <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Plan
            </div>
            <div className="mt-0.5 truncate text-sm font-medium text-foreground">
              {plan.goal}
            </div>
          </div>
          <span
            className={`rounded-full border px-2.5 py-1 text-xs font-medium ${statusBadgeClass(plan.status)}`}
          >
            {STATUS_LABELS[plan.status]}
          </span>
        </div>

        {plan.steps.length > 0 && (
          <div className="mt-3 max-h-44 overflow-y-auto pr-1">
            <div className="space-y-2">
              {plan.steps.map((step) => (
                <div
                  key={step.id}
                  className="grid grid-cols-[1.5rem_minmax(0,1fr)_5rem] items-start gap-2 text-sm"
                >
                  <span className="mt-1 flex h-5 w-5 items-center justify-center rounded-full bg-muted text-[10px] font-medium text-muted-foreground">
                    {step.id}
                  </span>
                  <div className="min-w-0">
                    <div className="break-words leading-5 text-foreground">
                      {step.description}
                    </div>
                    {(step.result || step.error) && (
                      <div className="mt-0.5 line-clamp-2 break-words text-xs text-muted-foreground">
                        {step.error || step.result}
                      </div>
                    )}
                  </div>
                  <div className="flex items-center justify-end gap-1.5 text-xs text-muted-foreground">
                    <span className={`h-2 w-2 rounded-full ${stepDotClass(step.status)}`} />
                    <span>{STEP_STATUS_LABELS[step.status]}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
