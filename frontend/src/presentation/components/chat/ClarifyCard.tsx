/**
 * 表现层 - 澄清问题卡片
 */
import React, { useCallback, useMemo, useState } from 'react';

export interface ClarifyPrompt {
  question: string;
  options: string[];
}

const QUESTION_RE = /\*\*Question\*\*\s*:\s*([\s\S]*?)(?:\n\s*\*\*Options\*\*\s*:|$)/i;
const OPTIONS_RE = /\*\*Options\*\*\s*:\s*([\s\S]*)$/i;

const cleanOption = (line: string): string =>
  line
    .replace(/^\s*(?:[-*]\s*)?(?:\d+[\s.、:：)]*)?/, '')
    .trim();

const isOtherOption = (option: string): boolean =>
  /^(其他|其它|other)\b/i.test(option.trim());

export const parseClarifyPrompt = (text?: string | null): ClarifyPrompt | null => {
  const value = (text || '').replace(/\r\n/g, '\n').trim();
  if (!value) return null;

  const questionMatch = value.match(QUESTION_RE);
  const question = questionMatch?.[1]?.trim();
  if (!question) return null;

  const optionsMatch = value.match(OPTIONS_RE);
  const options = optionsMatch
    ? optionsMatch[1]
        .split('\n')
        .map(cleanOption)
        .filter(Boolean)
    : [];

  return { question, options };
};

interface ClarifyCardProps {
  prompt: ClarifyPrompt;
  disabled?: boolean;
  timestamp?: string;
  onAnswer?: (answer: string) => void;
}

export const ClarifyCard: React.FC<ClarifyCardProps> = ({
  prompt,
  disabled = false,
  timestamp,
  onAnswer,
}) => {
  const [customAnswer, setCustomAnswer] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const canSubmit = !!onAnswer && !disabled && !submitted;
  const visibleOptions = useMemo(
    () => prompt.options.filter((option) => !isOtherOption(option)),
    [prompt.options],
  );

  const sendAnswer = useCallback(
    (answer: string) => {
      const trimmed = answer.trim();
      if (!trimmed || !canSubmit) return;
      setSubmitted(true);
      onAnswer?.(trimmed);
    },
    [canSubmit, onAnswer],
  );

  return (
    <div className="w-full max-w-[720px] rounded-xl border bg-card p-4 shadow-sm">
      <div className="mb-3">
        <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Clarify
        </div>
        <div className="mt-1 text-sm font-medium leading-6 text-foreground">
          {prompt.question}
        </div>
      </div>

      {visibleOptions.length > 0 && (
        <div className="space-y-2">
          {visibleOptions.map((option, index) => (
            <button
              key={`${option}-${index}`}
              type="button"
              disabled={!canSubmit}
              onClick={() => sendAnswer(option)}
              className="flex w-full items-start gap-3 rounded-lg border bg-background px-3 py-2 text-left text-sm transition-colors hover:border-primary/40 hover:bg-accent disabled:cursor-default disabled:opacity-70 disabled:hover:border-border disabled:hover:bg-background"
            >
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-medium text-muted-foreground">
                {index + 1}
              </span>
              <span className="min-w-0 flex-1 break-words leading-5">
                {option}
              </span>
            </button>
          ))}
        </div>
      )}

      <div className="mt-3">
        <label className="mb-1 block text-xs font-medium text-muted-foreground">
          其他：
        </label>
        <div className="flex gap-2">
          <input
            value={customAnswer}
            onChange={(event) => setCustomAnswer(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault();
                sendAnswer(customAnswer);
              }
            }}
            disabled={!canSubmit}
            placeholder="请输入你的回答"
            className="input h-9 flex-1"
          />
          <button
            type="button"
            disabled={!canSubmit || !customAnswer.trim()}
            onClick={() => sendAnswer(customAnswer)}
            className="btn btn-primary h-9 shrink-0 px-3 py-1 text-xs"
          >
            发送
          </button>
        </div>
      </div>

      <div className="mt-3 flex items-center justify-between border-t pt-2 text-[10px] text-muted-foreground">
        <span>{submitted ? '已发送' : canSubmit ? '待选择' : '已归档'}</span>
        {timestamp && <span>{new Date(timestamp).toLocaleTimeString()}</span>}
      </div>
    </div>
  );
};
