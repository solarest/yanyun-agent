/**
 * 表现层 - 聊天头部
 */
import React from 'react';
import { Link } from 'react-router-dom';
import type { Session } from '@domain/entities/session';
import type { AgentPhase } from '@domain/entities/task';

const PHASE_LABELS: Record<string, string> = {
  idle: '空闲',
  thinking: '思考中...',
  tool_executing: '工具调用中...',
  loop_correcting: '循环纠正中...',
  stuck_recovering: '恢复中...',
  context_compacting: '上下文压缩中...',
  complete: '完成',
  failed: '失败',
  cancelled: '已取消',
};

interface ChatHeaderProps {
  agentName: string;
  agentId: string;
  session: Session | null;
  isStreaming: boolean;
  currentPhase: AgentPhase;
  onCancel: () => void;
}

export const ChatHeader: React.FC<ChatHeaderProps> = ({
  agentName,
  agentId,
  session,
  isStreaming,
  currentPhase,
  onCancel,
}) => {
  return (
    <div className="flex items-center justify-between border-b bg-card px-4 py-3">
      <div className="flex items-center gap-3">
        <Link
          to="/agents"
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          &larr; 返回
        </Link>
        <div className="h-5 w-px bg-border" />
        <div>
          <h2 className="text-sm font-semibold">{agentName}</h2>
          {session && (
            <p className="text-xs text-muted-foreground">
              {session.title || '未命名'}
            </p>
          )}
        </div>
      </div>

      <div className="flex items-center gap-3">
        {isStreaming && (
          <>
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span className="h-2 w-2 animate-pulse rounded-full bg-primary" />
              {PHASE_LABELS[currentPhase] || currentPhase}
            </span>
            <button
              type="button"
              onClick={onCancel}
              className="btn btn-outline px-3 py-1 text-xs text-destructive hover:bg-destructive/10"
            >
              停止
            </button>
          </>
        )}
        <Link
          to={`/agents/${agentId}/edit`}
          className="btn btn-ghost px-3 py-1 text-xs"
        >
          设置
        </Link>
      </div>
    </div>
  );
};
