/**
 * 基础设施层 - 命令确认审批 API 客户端（task 7.1）
 */
import { apiClient } from './client';
import type { ApprovalDecision } from '@domain/entities/events';

export const approvalApi = {
  /** 提交用户对一条待确认危险命令的决策，唤醒对应挂起工具调用。 */
  postApproval(taskId: string, toolCallId: string, decision: ApprovalDecision) {
    return apiClient.post(`/tasks/${taskId}/approvals`, {
      toolCallId,
      decision,
    });
  },
};
