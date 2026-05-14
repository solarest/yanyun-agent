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
  timestamp,
  onAnswer,
}) => {
  const prompts = useMemo(() => parseAllClarifyPrompts(content), [content]);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [submitted, setSubmitted] = useState(false);
  
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
    
    // 按问题顺序收集答案
    const orderedAnswers = prompts.map((_, index) => answers[index] || '').filter(Boolean);
    
    setSubmitted(true);
    onAnswer?.(orderedAnswers);
  }, [canSubmit, onAnswer, prompts, answers]);
  
  if (prompts.length === 0) {
    return null;
  }
  
  // 如果只有一个问题，使用单问题样式
  if (prompts.length === 1) {
    const prompt = prompts[0];
    const visibleOptions = prompt.options.filter(
      (option) => !/^(其他|其它|other)\b/i.test(option.trim())
    );
    const selectedAnswer = answers[0];
    
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
                disabled={!onAnswer || disabled || submitted || selectedAnswer === option}
                onClick={() => handleOptionSelect(0, option)}
                className={`flex w-full items-start gap-3 rounded-lg border px-3 py-2 text-left text-sm transition-colors ${
                  selectedAnswer === option
                    ? 'border-primary bg-primary/10'
                    : 'bg-background hover:border-primary/40 hover:bg-accent'
                } disabled:cursor-default disabled:opacity-70`}
              >
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-medium text-muted-foreground">
                  {index + 1}
                </span>
                <span className="min-w-0 flex-1 break-words leading-5">{option}</span>
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
              value={answers[0] || ''}
              onChange={(e) => handleOptionSelect(0, e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  handleSubmit();
                }
              }}
              disabled={!onAnswer || disabled || submitted}
              placeholder="请输入你的回答"
              className="input h-9 flex-1"
            />
            <button
              type="button"
              disabled={!onAnswer || disabled || submitted || !answers[0]?.trim()}
              onClick={handleSubmit}
              className="btn btn-primary h-9 shrink-0 px-3 py-1 text-xs"
            >
              {submitted ? '已发送' : '发送'}
            </button>
          </div>
        </div>
        
        <div className="mt-3 flex items-center justify-between border-t pt-2 text-[10px] text-muted-foreground">
          <span>{submitted ? '已发送' : selectedAnswer ? '已选择' : '待选择'}</span>
          {timestamp && <span>{new Date(timestamp).toLocaleTimeString()}</span>}
        </div>
      </div>
    );
  }
  
  // 多个问题的样式
  return (
    <div className="w-full max-w-[720px] rounded-xl border bg-card p-4 shadow-sm">
      <div className="mb-4">
        <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Clarify ({answeredCount}/{totalQuestions})
        </div>
        <div className="mt-1 text-sm text-muted-foreground">
          请回答以下问题，全部回答完成后可统一提交
        </div>
      </div>
      
      <div className="space-y-4">
        {prompts.map((prompt, questionIndex) => {
          const visibleOptions = prompt.options.filter(
            (option) => !/^(其他|其它|other)\b/i.test(option.trim())
          );
          const selectedAnswer = answers[questionIndex];
          
          return (
            <div key={questionIndex} className="rounded-lg border bg-background p-3">
              <div className="mb-2">
                <div className="text-xs font-medium text-muted-foreground">
                  问题 {questionIndex + 1}
                </div>
                <div className="mt-1 text-sm font-medium leading-6 text-foreground">
                  {prompt.question}
                </div>
              </div>
              
              {visibleOptions.length > 0 && (
                <div className="space-y-1.5">
                  {visibleOptions.map((option, optionIndex) => (
                    <button
                      key={`${option}-${optionIndex}`}
                      type="button"
                      disabled={!onAnswer || disabled || submitted}
                      onClick={() => handleOptionSelect(questionIndex, option)}
                      className={`flex w-full items-start gap-2 rounded-md border px-2.5 py-1.5 text-left text-sm transition-colors ${
                        selectedAnswer === option
                          ? 'border-primary bg-primary/10'
                          : 'bg-card hover:border-primary/40 hover:bg-accent'
                      } disabled:cursor-default disabled:opacity-70`}
                    >
                      <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-muted text-[10px] font-medium text-muted-foreground">
                        {optionIndex + 1}
                      </span>
                      <span className="min-w-0 flex-1 break-words leading-5 text-xs">
                        {option}
                      </span>
                    </button>
                  ))}
                </div>
              )}
              
              <div className="mt-2">
                <input
                  value={selectedAnswer || ''}
                  onChange={(e) => handleOptionSelect(questionIndex, e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && allAnswered) {
                      e.preventDefault();
                      handleSubmit();
                    }
                  }}
                  disabled={!onAnswer || disabled || submitted}
                  placeholder={selectedAnswer ? '已回答' : '自定义回答...'}
                  className="input h-7 w-full text-xs"
                />
              </div>
              
              {selectedAnswer && (
                <div className="mt-1 text-xs text-primary">✓ 已选择: {selectedAnswer}</div>
              )}
            </div>
          );
        })}
      </div>
      
      <div className="mt-4 flex items-center justify-between border-t pt-3">
        <div className="text-xs text-muted-foreground">
          {submitted ? (
            <span className="text-primary">✓ 已提交所有回答</span>
          ) : (
            <span>
              已回答 {answeredCount}/{totalQuestions} 个问题
            </span>
          )}
        </div>
        <button
          type="button"
          disabled={!canSubmit}
          onClick={handleSubmit}
          className="btn btn-primary h-8 px-4 text-xs"
        >
          {submitted ? '已发送' : `提交全部回答 (${answeredCount}/${totalQuestions})`}
        </button>
      </div>
      
      {timestamp && (
        <div className="mt-2 text-right text-[10px] text-muted-foreground">
          {new Date(timestamp).toLocaleTimeString()}
        </div>
      )}
    </div>
  );
};
