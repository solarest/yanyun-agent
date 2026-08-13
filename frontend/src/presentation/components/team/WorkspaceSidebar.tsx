/**
 * 表现层 - Team 工作空间文件侧栏
 */
import React from 'react';

export interface WorkspaceFileEntry {
  name: string;
  path: string;
  is_dir: boolean;
  size: number;
  modified_at: number;
}

interface WorkspaceSidebarProps {
  files: WorkspaceFileEntry[];
  onRefresh: () => void;
}

const formatSize = (file: WorkspaceFileEntry): string => {
  if (file.is_dir) return '';
  return file.size > 1024 ? `${(file.size / 1024).toFixed(1)}KB` : `${file.size}B`;
};

export const WorkspaceSidebar: React.FC<WorkspaceSidebarProps> = ({ files, onRefresh }) => (
  <div className="w-64 flex-shrink-0 border-l bg-card/30 overflow-y-auto">
    <div className="p-3 border-b bg-card/50 flex items-center justify-between">
      <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">工作空间</h3>
      <button
        type="button"
        onClick={onRefresh}
        className="text-xs text-muted-foreground/50 hover:text-muted-foreground transition-colors"
      >
        刷新
      </button>
    </div>
    {files.length === 0 ? (
      <div className="p-4 text-center text-xs text-muted-foreground/50">暂无文件</div>
    ) : (
      <div className="divide-y divide-border/20">
        {files.map((f) => (
          <div key={f.path} className="px-3 py-2 flex items-center gap-2 text-xs">
            <span className="shrink-0">{f.is_dir ? '📁' : '📄'}</span>
            <span className="flex-1 truncate text-muted-foreground">{f.name}</span>
            <span className="shrink-0 text-muted-foreground/40 text-[10px]">{formatSize(f)}</span>
          </div>
        ))}
      </div>
    )}
  </div>
);
