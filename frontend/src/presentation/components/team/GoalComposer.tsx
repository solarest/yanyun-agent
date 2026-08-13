/**
 * 表现层 - Team 目标输入区（idle 状态）
 */
import React, { useState } from 'react';

interface GoalComposerProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  disabled?: boolean;
  buttonLabel?: string;
  error?: string | null;
}

export const GoalComposer: React.FC<GoalComposerProps> = ({
  value,
  onChange,
  onSubmit,
  disabled = false,
  buttonLabel = '开始执行',
  error,
}) => {
  const [focused, setFocused] = useState(false);

  return (
    <div className="flex-1 flex flex-col items-center justify-center p-4">
      <div className="w-full max-w-2xl">
        <h2 className="mb-6 text-center text-xl font-semibold">团队目标</h2>
        <div className={`rounded-2xl border bg-card transition-colors ${focused ? 'border-primary/30 shadow-sm' : 'border-border'}`}>
          <textarea
            className="w-full resize-none bg-transparent px-4 py-3 text-sm placeholder:text-muted-foreground/50 focus:outline-none"
            rows={4}
            placeholder="描述你的团队目标..."
            value={value}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                onSubmit();
              }
            }}
          />
          <div className="flex items-center justify-between border-t border-border/50 px-3 py-2">
            <span className="text-[10px] text-muted-foreground/40">⌘ + Enter 开始执行</span>
            <button
              type="button"
              className="btn btn-primary text-sm"
              disabled={!value.trim() || disabled}
              onClick={onSubmit}
            >
              {buttonLabel}
            </button>
          </div>
        </div>
        {error && (
          <div className="mt-3 rounded-lg border border-destructive/20 bg-destructive/5 p-3 text-sm text-destructive">
            {error}
          </div>
        )}
      </div>
    </div>
  );
};
