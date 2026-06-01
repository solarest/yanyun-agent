/**
 * 表现层 - 多澄清问题卡片
 * 
 * 支持同时显示多个 clarify 问题，用户回答完所有问题后统一提交。
 */
import React, { useCallback, useMemo, useState } from 'react';
import type { ClarifyPrompt } from './ClarifyCard';
import { parseClarifyPrompt } from './ClarifyCard';

export interface MultiClarifyPrompt {
  prompts: ClarifyPrompt[];
}

interface MultiClarifyCardProps {
  content: string;
  disabled?: boolean;
  /** 外部控制提交状态：true 时显示已回复记录，false 时显示交互表单 */
  submitted?: boolean;
  timestamp?: string;
  onAnswer?: (answers: string[]) => void;
}

/**
 * 从消息内容中解析所有 clarify 问题
 * 支持从 tool_results 或 content 中提取
 */
export const parseAllClarifyPrompts = (content: string): ClarifyPrompt[] => {
  const prompts: ClarifyPrompt[] = [];
  
  // 尝试按 **Question** 分割多个问题
  const questionBlocks = content.split(/\*\*Question\*\*/i);
  
  for (const block of questionBlocks) {
    // 跳过空块和纯空白块（防御性措施，避免 split 开头的空字符串）
    if (!block || !block.trim()) {
      continue;
    }
    
    const prompt = parseClarifyPrompt(`**Question**${block}`);
    if (prompt) {
      prompts.push(prompt);
    }
  }
  
  return prompts;
};

export const MultiClarifyCard: React.FC<MultiClarifyCardProps> = ({
  content,
  disabled = false,
  submitted: externalSubmitted = false,
  timestamp,
  onAnswer,
}) => {
  const prompts = useMemo(() => parseAllClarifyPrompts(content), [content]);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [internalSubmitted, setInternalSubmitted] = useState(false);
  const [submittedAnswers, setSubmittedAnswers] = useState<Record<number, string>>({});

  const submitted = externalSubmitted || internalSubmitted;
  const totalQuestions = prompts.length;
  const answeredCount = Object.keys(answers).length;
  const allAnswered = answeredCount === totalQuestions && totalQuestions > 0;
  const canSubmit = !!onAnswer && !disabled && !submitted && allAnswered;

  const handleOptionSelect = useCallback((questionIndex: number, answer: string) => {
    setAnswers((prev) => ({
      ...prev,
      [questionIndex]: answer,
    }));
  }, []);

  const handleSubmit = useCallback(() => {
    if (!canSubmit) return;
    const orderedAnswers = prompts.map((_, index) => answers[index] || '').filter(Boolean);
    setInternalSubmitted(true);
    setSubmittedAnswers({ ...answers });
    onAnswer?.(orderedAnswers);
  }, [canSubmit, onAnswer, prompts, answers]);

  if (prompts.length === 0) return null;

  // 已提交态：显示所有问答记录
  if (submitted) {
    return (
      <div className="my-2 border-l-2 border-muted-foreground/20 pl-3">
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground/60 mb-1.5">
          <span className="inline-block w-1 h-1 rounded-full bg-emerald-400" />
          <span>已回复 {totalQuestions} 个问题</span>
          {timestamp && (
            <span className="text-muted-foreground/40">
              {new Date(timestamp).toLocaleTimeString()}
            </span>
          )}
        </div>
        <div className="space-y-1">
          {prompts.map((prompt, idx) => (
            <div key={idx} className="text-sm text-muted-foreground/70">
              <span className="text-muted-foreground/50">{prompt.question}</span>
              <span className="mx-1.5 text-muted-foreground/30">→</span>
              <span className="text-foreground/80">{submittedAnswers[idx] || '—'}</span>
            </div>
          ))}
        </div>
      </div>
    );
  }

  // 只有一个问题：复用单问题布局
  if (prompts.length === 1) {
    const prompt = prompts[0];
    const visibleOptions = prompt.options.filter(
      (option) => !/^(其他|其它|other)\b/i.test(option.trim())
    );
    const selectedAnswer = answers[0];

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
                disabled={!onAnswer || disabled || submitted}
                onClick={() => handleOptionSelect(0, option)}
                className={`flex w-full items-start gap-2 rounded-md border px-2.5 py-1.5 text-left text-sm transition-colors ${
                  selectedAnswer === option
                    ? 'border-primary/40 bg-primary/5'
                    : 'border-border/60 bg-background hover:border-primary/30 hover:bg-accent/50'
                } disabled:cursor-default disabled:opacity-60`}
              >
                <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-muted text-[10px] text-muted-foreground">
                  {index + 1}
                </span>
                <span className="min-w-0 flex-1 break-words leading-5 text-sm">{option}</span>
              </button>
            ))}
          </div>
        )}

        <div className="flex gap-2">
          <input
            value={answers[0] || ''}
            onChange={(e) => handleOptionSelect(0, e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') { e.preventDefault(); handleSubmit(); }
            }}
            disabled={!onAnswer || disabled || submitted}
            placeholder="或输入其他回答…"
            className="input h-8 flex-1 text-sm"
          />
          <button
            type="button"
            disabled={!onAnswer || disabled || submitted || !answers[0]?.trim()}
            onClick={handleSubmit}
            className="btn btn-primary h-8 shrink-0 px-3 text-xs"
          >
            发送
          </button>
        </div>
      </div>
    );
  }

  // 多个问题
  return (
    <div className="my-2 border-l-2 border-muted-foreground/20 pl-3">
      <div className="mb-3">
        <div className="text-xs text-muted-foreground/60">
          需要补充信息 · {answeredCount}/{totalQuestions}
        </div>
        <div className="mt-0.5 text-xs text-muted-foreground/50">
          请回答以下问题，完成后统一提交
        </div>
      </div>

      <div className="space-y-3">
        {prompts.map((prompt, questionIndex) => {
          const visibleOptions = prompt.options.filter(
            (option) => !/^(其他|其它|other)\b/i.test(option.trim())
          );
          const selectedAnswer = answers[questionIndex];

          return (
            <div key={questionIndex}>
              <div className="mb-1.5 text-sm text-foreground/85 leading-6">
                {prompt.question}
              </div>

              {visibleOptions.length > 0 && (
                <div className="space-y-1 mb-1.5">
                  {visibleOptions.map((option, optionIndex) => (
                    <button
                      key={`${option}-${optionIndex}`}
                      type="button"
                      disabled={!onAnswer || disabled || submitted}
                      onClick={() => handleOptionSelect(questionIndex, option)}
                      className={`flex w-full items-start gap-2 rounded-md border px-2 py-1 text-left text-xs transition-colors ${
                        selectedAnswer === option
                          ? 'border-primary/40 bg-primary/5'
                          : 'border-border/60 bg-background hover:border-primary/30 hover:bg-accent/50'
                      } disabled:cursor-default disabled:opacity-60`}
                    >
                      <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-muted text-[10px] text-muted-foreground">
                        {optionIndex + 1}
                      </span>
                      <span className="min-w-0 flex-1 break-words leading-5">{option}</span>
                    </button>
                  ))}
                </div>
              )}

              <input
                value={selectedAnswer || ''}
                onChange={(e) => handleOptionSelect(questionIndex, e.target.value)}
                disabled={!onAnswer || disabled || submitted}
                placeholder="或输入其他回答…"
                className="input h-7 w-full text-xs"
              />
            </div>
          );
        })}
      </div>

      <div className="mt-3 flex items-center justify-between">
        <span className="text-xs text-muted-foreground/50">
          {answeredCount}/{totalQuestions} 已答
        </span>
        <button
          type="button"
          disabled={!canSubmit}
          onClick={handleSubmit}
          className="btn btn-primary h-7 px-3 text-xs"
        >
          提交全部回答
        </button>
      </div>
    </div>
  );
};
