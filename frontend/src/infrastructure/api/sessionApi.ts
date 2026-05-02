/**
 * 基础设施层 - Session 会话 API 客户端
 */
import { apiClient } from './client';
import type {
  CreateSessionRequest,
  SendMessageRequest,
  SendMessageResponse,
  Session,
  SessionDetailResponse,
  SessionListResponse,
  UpdateSessionRequest,
} from '../../domain/entities/session';

export const sessionApi = {
  /**
   * 创建会话
   */
  createSession: async (agentId: string, request: CreateSessionRequest = {}): Promise<Session> => {
    const response = await apiClient.post<Session>(
      `/agents/${agentId}/sessions`,
      request,
    );
    return response.data;
  },

  /**
   * 获取会话列表
   */
  listSessions: async (agentId: string, page = 1, pageSize = 20): Promise<SessionListResponse> => {
    const response = await apiClient.get<SessionListResponse>(
      `/agents/${agentId}/sessions`,
      { params: { page, page_size: pageSize } },
    );
    return response.data;
  },

  /**
   * 获取会话详情（含消息历史）
   */
  getSessionDetail: async (agentId: string, sessionId: string): Promise<SessionDetailResponse> => {
    const response = await apiClient.get<SessionDetailResponse>(
      `/agents/${agentId}/sessions/${sessionId}`,
    );
    return response.data;
  },

  /**
   * 更新会话
   */
  updateSession: async (
    agentId: string,
    sessionId: string,
    request: UpdateSessionRequest,
  ): Promise<Session> => {
    const response = await apiClient.patch<Session>(
      `/agents/${agentId}/sessions/${sessionId}`,
      request,
    );
    return response.data;
  },

  /**
   * 删除会话
   */
  deleteSession: async (agentId: string, sessionId: string): Promise<void> => {
    await apiClient.delete(`/agents/${agentId}/sessions/${sessionId}`);
  },

  /**
   * 发送消息（触发 Agent Loop）
   */
  sendMessage: async (
    agentId: string,
    sessionId: string,
    request: SendMessageRequest,
  ): Promise<SendMessageResponse> => {
    const response = await apiClient.post<SendMessageResponse>(
      `/agents/${agentId}/sessions/${sessionId}/messages`,
      request,
    );
    return response.data;
  },
};
