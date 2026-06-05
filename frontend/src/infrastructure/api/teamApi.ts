/**
 * 基础设施层 - Team API 客户端
 */
import { apiClient } from './client';
import type {
  Team,
  TeamDetail,
  TeamListResponse,
  CreateTeamRequest,
  UpdateTeamRequest,
  ExecuteTeamRequest,
  ExecuteTeamResponse,
} from '@domain/entities/team';

export const teamApi = {
  /** 获取 Team 列表 */
  list: async (params?: {
    page?: number;
    pageSize?: number;
  }): Promise<TeamListResponse> => {
    const response = await apiClient.get('/teams', {
      params: {
        page: params?.page ?? 1,
        page_size: params?.pageSize ?? 20,
      },
    });
    return response.data;
  },

  /** 获取 Team 详情 */
  get: async (id: string): Promise<TeamDetail> => {
    const response = await apiClient.get(`/teams/${id}`);
    return response.data;
  },

  /** 创建 Team */
  create: async (data: CreateTeamRequest): Promise<Team> => {
    const response = await apiClient.post('/teams', data);
    return response.data;
  },

  /** 更新 Team */
  update: async (id: string, data: UpdateTeamRequest): Promise<Team> => {
    const response = await apiClient.put(`/teams/${id}`, data);
    return response.data;
  },

  /** 删除 Team */
  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/teams/${id}`);
  },

  /** 获取团队成员列表 */
  listMembers: async (teamId: string) => {
    const response = await apiClient.get(`/teams/${teamId}/members`);
    return response.data;
  },

  /** 执行团队目标 */
  execute: async (
    teamId: string,
    data: ExecuteTeamRequest
  ): Promise<ExecuteTeamResponse> => {
    const response = await apiClient.post(`/teams/${teamId}/execute`, data);
    return response.data;
  },
};
