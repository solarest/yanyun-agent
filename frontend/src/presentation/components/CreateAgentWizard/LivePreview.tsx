/**
 * 表现层 - 实时预览面板
 */
import React from 'react';
import { VIBE_LABELS } from '@application/services/useAgentGenerator';
import type { GeneratedContent } from '@application/services/useAgentGenerator';

interface LivePreviewProps {
  name: string;
  description: string;
  vibes: string[];
  generated: GeneratedContent | null;
}

/** 基于名称生成显示颜色 */
function getAvatarColor(name: string): string {
  const colors = [
    '#6366f1', '#8b5cf6', '#ec4899', '#f43f5e',
    '#f97316', '#eab308', '#22c55e', '#06b6d4',
    '#3b82f6', '#a855f7', '#14b8a6', '#f59e0b',
  ];
  const hash = name.split('').reduce((a, c) => a + c.charCodeAt(0), 0);
  return colors[hash % colors.length];
}

/** 从 SOUL.md 内容中提取座右铭 */
function extractQuote(soulMd: string): string {
  const match = soulMd.match(/"([^"]+)"/);
  return match ? match[1] : '';
}

export const LivePreview: React.FC<LivePreviewProps> = ({
  name,
  description,
  vibes,
  generated,
}) => {
  const quote = generated ? extractQuote(generated.soul_md) : '';

  return (
    <div className="rounded-xl border bg-card p-6">
      <h3 className="mb-4 text-sm font-medium text-muted-foreground">
        Live Preview
      </h3>

      <div className="flex flex-col items-center text-center">
        {/* 头像 */}
        <div
          className="mb-4 flex h-20 w-20 items-center justify-center rounded-full text-2xl font-bold text-white"
          style={{
            backgroundColor: name ? getAvatarColor(name) : '#94a3b8',
          }}
        >
          {name ? name.charAt(0).toUpperCase() : '?'}
        </div>

        {/* 名称 */}
        <h4 className="mb-2 text-lg font-semibold">
          {name || '未命名 Agent'}
        </h4>

        {/* Vibe 标签 */}
        {vibes.length > 0 && (
          <div className="mb-3 flex flex-wrap justify-center gap-1.5">
            {vibes.map((v) => (
              <span
                key={v}
                className="rounded-full bg-primary/10 px-2.5 py-0.5 text-xs font-medium text-primary"
              >
                {VIBE_LABELS[v] ?? v}
              </span>
            ))}
          </div>
        )}

        {/* 座右铭 */}
        {quote && (
          <p className="mb-3 text-sm italic text-muted-foreground">
            "{quote}"
          </p>
        )}

        {/* 描述 */}
        {description && (
          <p className="text-sm text-muted-foreground">{description}</p>
        )}
      </div>
    </div>
  );
};
