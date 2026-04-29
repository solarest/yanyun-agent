/**
 * 表现层 - 删除 Agent 确认对话框
 */
import React from 'react';

interface DeleteAgentDialogProps {
  isOpen: boolean;
  agentName: string;
  onConfirm: () => void;
  onCancel: () => void;
  isLoading: boolean;
}

export const DeleteAgentDialog: React.FC<DeleteAgentDialogProps> = ({
  isOpen,
  agentName,
  onConfirm,
  onCancel,
  isLoading,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-md rounded-lg border bg-card p-6 shadow-lg">
        <h3 className="mb-2 text-lg font-semibold">Delete Agent</h3>
        <p className="mb-6 text-sm text-muted-foreground">
          Are you sure you want to delete <strong>{agentName}</strong>? This
          action cannot be undone.
        </p>
        <div className="flex justify-end gap-2">
          <button
            type="button"
            className="btn btn-outline"
            onClick={onCancel}
            disabled={isLoading}
          >
            Cancel
          </button>
          <button
            type="button"
            className="btn bg-destructive text-destructive-foreground hover:bg-destructive/90"
            onClick={onConfirm}
            disabled={isLoading}
          >
            {isLoading ? 'Deleting...' : 'Delete'}
          </button>
        </div>
      </div>
    </div>
  );
};
