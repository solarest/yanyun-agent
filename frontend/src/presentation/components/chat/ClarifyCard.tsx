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
  /** 外部控制提交状态：true 时显示已回复记录，false 时显示交互表单 */
  submitted?: boolean;
  timestamp?: string;
  onAnswer?: (answer: string) => void;
}

export const ClarifyCard: React.FC<ClarifyCardProps> = ({
  prompt,
  disabled = false,
  submitted: externalSubmitted = false,
  timestamp,
  onAnswer,
}) => {
  const [customAnswer, setCustomAnswer] = useState('');
  const [internalSubmitted, setInternalSubmitted] = useState(false);
  const [submittedAnswer, setSubmittedAnswer] = useState('');

  const submitted = externalSubmitted || internalSubmitted;
  const canSubmit = !!onAnswer && !disabled && !submitted;
  const visibleOptions = useMemo(
    () => prompt.options.filter((option) => !isOtherOption(option)),
    [prompt.options],
  );

  const sendAnswer = useCallback(
    (answer: string) => {
      const trimmed = answer.trim();
      if (!trimmed || !canSubmit) return;
      setInternalSubmitted(true);
      setSubmittedAnswer(trimmed);
      onAnswer?.(trimmed);
    },
    [canSubmit, onAnswer],
  );

  // 已提交态：显示问答记录
  if (submitted) {
    return (
      <div className="my-2 border-l-2 border-muted-foreground/20 pl-3">
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground/60">
          <span className="inline-block w-1 h-1 rounded-full bg-emerald-400" />
          <span>已回复</span>
          {timestamp && (
            <span className="text-muted-foreground/40">
              {new Date(timestamp).toLocaleTimeString()}
            </span>
          )}
        </div>
        <div className="mt-0.5 text-sm text-muted-foreground/70">
          <span className="text-muted-foreground/50">{prompt.question}</span>
          <span className="mx-1.5 text-muted-foreground/30">→</span>
          <span className="text-foreground/80">{submittedAnswer}</span>
        </div>
      </div>
    );
  }

  return (
    <div className="my-2 border-l-2 border-muted-foreground/20 pl-3">
      <div className="mb-2">
        <div className="text-xs text-muted-foreground/60">需要补充信息</div>
        <div className="mt-0.5 text-sm text-foreground/90 leading-6">
          {prompt.question}
        </div>
      </div>

      {visibleOptions.length > 0 && (
        <div className="space-y-1.5 mb-2">
          {visibleOptions.map((option, index) => (
            <button
              key={`${option}-${index}`}
              type="button"
              disabled={!canSubmit}
              onClick={() => sendAnswer(option)}
              className="flex w-full items-start gap-2 rounded-md border border-border/60 bg-background px-2.5 py-1.5 text-left text-sm transition-colors hover:border-primary/30 hover:bg-accent/50 disabled:cursor-default disabled:opacity-60"
            >
              <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-muted text-[10px] text-muted-foreground">
                {index + 1}
              </span>
              <span className="min-w-0 flex-1 break-words leading-5 text-sm">
                {option}
              </span>
            </button>
          ))}
        </div>
      )}

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
          placeholder="或输入其他回答…"
          className="input h-8 flex-1 text-sm"
        />
        <button
          type="button"
          disabled={!canSubmit || !customAnswer.trim()}
          onClick={() => sendAnswer(customAnswer)}
          className="btn btn-primary h-8 shrink-0 px-3 text-xs"
        >
          发送
        </button>
      </div>
    </div>
  );
};
