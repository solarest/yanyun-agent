/**
 * 表现层 - 会话侧边栏
 */
import React from 'react';
import type { Session } from '@domain/entities/session';

interface SessionSidebarProps {
  sessions: Session[];
  currentSessionId: string | null;
  isLoading: boolean;
  onSelectSession: (sessionId: string) => void;
  onNewSession: () => void;
  onDeleteSession: (sessionId: string) => void;
}

export const SessionSidebar: React.FC<SessionSidebarProps> = ({
  sessions,
  currentSessionId,
  isLoading,
  onSelectSession,
  onNewSession,
  onDeleteSession,
}) => {
  return (
    <div className="flex h-full w-64 flex-col border-r bg-card">
      {/* 新建按钮 */}
      <div className="border-b p-3">
        <button
          type="button"
          onClick={onNewSession}
          className="btn btn-primary w-full text-sm"
        >
          + New Chat
        </button>
      </div>

      {/* 会话列表 */}
      <div className="flex-1 overflow-y-auto">
        {isLoading && sessions.length === 0 && (
          <div className="p-4 text-center text-sm text-muted-foreground">
            Loading...
          </div>
        )}

        {!isLoading && sessions.length === 0 && (
          <div className="p-4 text-center text-sm text-muted-foreground">
            No conversations yet
          </div>
        )}

        {sessions.map((session) => (
          <div
            key={session.id}
            className={`group relative cursor-pointer border-b px-3 py-3 transition-colors hover:bg-accent/50 ${
              session.id === currentSessionId ? 'bg-accent' : ''
            }`}
            onClick={() => onSelectSession(session.id)}
          >
            <div className="truncate text-sm font-medium">
              {session.title || 'Untitled'}
            </div>
            {session.last_message_preview && (
              <div className="mt-0.5 truncate text-xs text-muted-foreground">
                {session.last_message_preview}
              </div>
            )}
            <div className="mt-1 flex items-center justify-between">
              <span className="text-xs text-muted-foreground">
                {new Date(session.created_at).toLocaleDateString()}
              </span>
              <button
                type="button"
                className="hidden rounded p-0.5 text-xs text-muted-foreground hover:text-destructive group-hover:block"
                onClick={(e) => {
                  e.stopPropagation();
                  onDeleteSession(session.id);
                }}
              >
                Delete
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
