/**
 * 表现层 - 消息输入框
 */
import React, { useState, useCallback, useRef, useEffect } from 'react';

interface MessageInputProps {
  onSend: (content: string) => void;
  disabled?: boolean;
  placeholder?: string;
  /** 左侧操作按钮区域（如 "+" 技能选择按钮） */
  leftActions?: React.ReactNode;
}

export const MessageInput: React.FC<MessageInputProps> = ({
  onSend,
  disabled = false,
  placeholder = '输入消息...',
  leftActions,
}) => {
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // 自动调整高度
  useEffect(() => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = 'auto';
      el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
    }
  }, [value]);

  const handleSubmit = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue('');
  }, [value, disabled, onSend]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit],
  );

  return (
    <div className="border-t bg-card px-4 py-3">
      <div className="mx-auto flex max-w-3xl items-end gap-2">
        {leftActions && (
          <div className="flex shrink-0 items-center pb-1">{leftActions}</div>
        )}
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled}
          rows={1}
          className="textarea flex-1 resize-none text-sm"
        />
        <button
          type="button"
          onClick={handleSubmit}
          disabled={disabled || !value.trim()}
          className="btn btn-primary shrink-0 px-4 py-2 text-sm disabled:opacity-50"
        >
          Send
        </button>
      </div>
      <p className="mx-auto mt-1 max-w-3xl text-right text-[10px] text-muted-foreground">
        回车发送，Shift+回车换行
      </p>
    </div>
  );
};
