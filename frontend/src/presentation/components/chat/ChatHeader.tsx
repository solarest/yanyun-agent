/**
 * 表现层 - 聊天头部
 */
import React from 'react';
import { Link } from 'react-router-dom';
import type { Session } from '@domain/entities/session';
import type { AgentPhase } from '@domain/entities/task';

const PHASE_LABELS: Record<string, string> = {
  idle: 'Idle',
  thinking: 'Thinking...',
  tool_executing: 'Using tools...',
  loop_correcting: 'Correcting loop...',
  stuck_recovering: 'Recovering...',
  context_compacting: 'Compacting...',
  complete: 'Done',
  failed: 'Failed',
  cancelled: 'Cancelled',
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
          &larr; Back
        </Link>
        <div className="h-5 w-px bg-border" />
        <div>
          <h2 className="text-sm font-semibold">{agentName}</h2>
          {session && (
            <p className="text-xs text-muted-foreground">
              {session.title || 'Untitled'}
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
              Stop
            </button>
          </>
        )}
        <Link
          to={`/agents/${agentId}/edit`}
          className="btn btn-ghost px-3 py-1 text-xs"
        >
          Settings
        </Link>
      </div>
    </div>
  );
};
