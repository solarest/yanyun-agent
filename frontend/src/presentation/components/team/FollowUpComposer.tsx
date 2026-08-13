/**
 * 表现层 - Team 追问输入区
 *
 * 自动调整高度（上限 120px），Enter 发送 / Shift+Enter 换行。
 */
import React, { useEffect, useRef } from 'react';

interface FollowUpComposerProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  disabled?: boolean;
  runningLabel?: string;
}

export const FollowUpComposer: React.FC<FollowUpComposerProps> = ({
  value,
  onChange,
  onSubmit,
  disabled = false,
  runningLabel = '执行中...',
}) => {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // 自动调整高度（与 MessageInput 一致）
  useEffect(() => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = 'auto';
      el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
    }
  }, [value]);

  return (
    <div className="border-t bg-card px-4 py-3">
      <div className="mx-auto flex max-w-3xl items-end gap-3">
        <textarea
          ref={textareaRef}
          className="flex-1 resize-none rounded-xl border border-border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground/50 focus:border-primary/30 focus:outline-none focus:ring-0"
          rows={1}
          placeholder="继续追问..."
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              onSubmit();
            }
          }}
        />
        <button
          type="button"
          className="btn btn-primary shrink-0 text-sm"
          disabled={!value.trim() || disabled}
          onClick={onSubmit}
        >
          {runningLabel}
        </button>
      </div>
    </div>
  );
};
