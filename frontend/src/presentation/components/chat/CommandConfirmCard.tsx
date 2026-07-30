/**
 * 表现层 - 危险命令确认卡片（task 7.2）
 *
 * 克隆 ClarifyCard 形态：受控的 submitted / disabled、只读已应答态。
 * 三按钮：本次允许 / 全部允许 / 拒绝。
 */
import React, { useCallback, useState } from 'react';
import type { ApprovalDecision } from '@domain/entities/events';

interface CommandConfirmCardProps {
  command: string;
  riskReason?: string;
  disabled?: boolean;
  /** 外部控制提交状态：true 时显示已处理记录，false 时显示交互按钮 */
  submitted?: boolean;
  timestamp?: string;
  onDecision?: (decision: ApprovalDecision) => void;
}

const DECISIONS: { value: ApprovalDecision; label: string; destructive?: boolean }[] = [
  { value: 'allow_once', label: '本次允许' },
  { value: 'allow_all', label: '全部允许' },
  { value: 'deny', label: '拒绝', destructive: true },
];

const labelFor = (d: ApprovalDecision | null): string =>
  d === 'allow_once'
    ? '本次允许'
    : d === 'allow_all'
      ? '全部允许'
      : d === 'deny'
        ? '拒绝'
        : '已处理';

export const CommandConfirmCard: React.FC<CommandConfirmCardProps> = ({
  command,
  riskReason,
  disabled = false,
  submitted: externalSubmitted = false,
  timestamp,
  onDecision,
}) => {
  const [internalSubmitted, setInternalSubmitted] = useState(false);
  const [chosen, setChosen] = useState<ApprovalDecision | null>(null);
  const submitted = externalSubmitted || internalSubmitted;
  const canSubmit = !!onDecision && !disabled && !submitted;

  const decide = useCallback(
    (decision: ApprovalDecision) => {
      if (!canSubmit) return;
      setInternalSubmitted(true);
      setChosen(decision);
      onDecision?.(decision);
    },
    [canSubmit, onDecision],
  );

  // 已提交态：显示处理记录
  if (submitted) {
    return (
      <div className="my-2 border-l-2 border-amber-400/40 pl-3">
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground/60">
          <span className="inline-block h-1 w-1 rounded-full bg-amber-400" />
          <span>已确认：{labelFor(chosen)}</span>
          {timestamp && (
            <span className="text-muted-foreground/40">
              {new Date(timestamp).toLocaleTimeString()}
            </span>
          )}
        </div>
        <div className="mt-0.5 break-all font-mono text-sm text-muted-foreground/70">
          {command}
        </div>
      </div>
    );
  }

  return (
    <div className="my-2 border-l-2 border-amber-400/40 pl-3">
      <div className="mb-2">
        <div className="text-xs text-amber-500/80">⚠ 危险命令待确认</div>
        <div className="mt-0.5 break-all font-mono text-sm leading-6 text-foreground/90">
          {command}
        </div>
        {riskReason && (
          <div className="mt-1 text-xs text-muted-foreground/70">原因：{riskReason}</div>
        )}
      </div>
      <div className="flex flex-wrap gap-2">
        {DECISIONS.map((d) => (
          <button
            key={d.value}
            type="button"
            disabled={!canSubmit}
            onClick={() => decide(d.value)}
            className={
              'flex items-center rounded-md border px-3 py-1.5 text-left text-sm transition-colors disabled:cursor-default disabled:opacity-60 ' +
              (d.destructive
                ? 'border-destructive/40 bg-destructive/5 hover:border-destructive/60 hover:bg-destructive/10'
                : 'border-border/60 bg-background hover:border-primary/30 hover:bg-accent/50')
            }
          >
            {d.label}
          </button>
        ))}
      </div>
    </div>
  );
};
