/**
 * 基础设施层 - Skill API 客户端（ZIP 上传模式）
 */
import { apiClient } from './client';
import type { Skill, SkillListResponse } from '../../domain/entities/skill';

export const skillApi = {
  /** 获取 Skill 列表 */
  list: async (params?: {
    page?: number;
    pageSize?: number;
    category?: string;
    enabled?: boolean;
  }): Promise<SkillListResponse> => {
    const response = await apiClient.get<SkillListResponse>('/skills', {
      params: {
        page: params?.page ?? 1,
        page_size: params?.pageSize ?? 20,
        category: params?.category,
        enabled: params?.enabled,
      },
    });
    return response.data;
  },

  /** 获取 Skill 详情 */
  get: async (id: string): Promise<Skill> => {
    const response = await apiClient.get<Skill>(`/skills/${id}`);
    return response.data;
  },

  /** 上传 ZIP 创建 Skill */
  upload: async (file: File): Promise<Skill> => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await apiClient.post<Skill>('/skills/upload', formData, {
      headers: { 'Content-Type': undefined as unknown as string },
    });
    return response.data;
  },

  /** 重新上传 ZIP 更新 Skill */
  reupload: async (id: string, file: File): Promise<Skill> => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await apiClient.put<Skill>(`/skills/${id}/upload`, formData, {
      headers: { 'Content-Type': undefined as unknown as string },
    });
    return response.data;
  },

  /** 删除 Skill */
  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/skills/${id}`);
  },

  /** 切换启用状态 */
  toggle: async (id: string): Promise<Skill> => {
    const response = await apiClient.patch<Skill>(`/skills/${id}/toggle`);
    return response.data;
  },

  /** 获取所有启用的 Skills（对话选择用） */
  listEnabled: async (): Promise<SkillListResponse> => {
    const response = await apiClient.get<SkillListResponse>('/skills/enabled');
    return response.data;
  },
};
