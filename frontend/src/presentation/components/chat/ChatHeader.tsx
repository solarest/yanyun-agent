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
  paused: 'Waiting approval',
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
  pendingApprovalToolName?: string | null;
  onCancel: () => void;
  onApprove?: () => void;
  onDeny?: () => void;
}

export const ChatHeader: React.FC<ChatHeaderProps> = ({
  agentName,
  agentId,
  session,
  isStreaming,
  currentPhase,
  pendingApprovalToolName,
  onCancel,
  onApprove,
  onDeny,
}) => {
  const isPausedForApproval = currentPhase === 'paused' && !!pendingApprovalToolName;

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
        {(isStreaming || isPausedForApproval) && (
          <>
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <span className="h-2 w-2 animate-pulse rounded-full bg-primary" />
              {PHASE_LABELS[currentPhase] || currentPhase}
            </span>
            {isPausedForApproval ? (
              <>
                <span className="text-xs text-muted-foreground">
                  `{pendingApprovalToolName}`
                </span>
                <button
                  type="button"
                  onClick={onApprove}
                  className="btn btn-outline px-3 py-1 text-xs text-foreground hover:bg-accent"
                >
                  Approve
                </button>
                <button
                  type="button"
                  onClick={onDeny}
                  className="btn btn-outline px-3 py-1 text-xs text-destructive hover:bg-destructive/10"
                >
                  Deny
                </button>
              </>
            ) : (
              <button
                type="button"
                onClick={onCancel}
                className="btn btn-outline px-3 py-1 text-xs text-destructive hover:bg-destructive/10"
              >
                Stop
              </button>
            )}
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
