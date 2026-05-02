/**
 * 基础设施层 - 任务 API 客户端
 */
import { apiClient } from './client';
import type { CreateTaskRequest, Task, TaskListResponse } from '../../domain/entities/task';

export const taskApi = {
  /**
   * 创建新任务
   */
  createTask: async (request: CreateTaskRequest): Promise<Task> => {
    const response = await apiClient.post<Task>('/tasks', request);
    return response.data;
  },

  /**
   * 获取任务列表
   */
  listTasks: async (page = 1, pageSize = 20): Promise<TaskListResponse> => {
    const response = await apiClient.get<TaskListResponse>('/tasks', {
      params: { page, page_size: pageSize },
    });
    return response.data;
  },

  /**
   * 获取任务详情
   */
  getTask: async (taskId: string): Promise<Task> => {
    const response = await apiClient.get<Task>(`/tasks/${taskId}`);
    return response.data;
  },

  /**
   * 取消任务
   */
  cancelTask: async (taskId: string): Promise<void> => {
    await apiClient.post(`/tasks/${taskId}/cancel`);
  },

  resolveApproval: async (taskId: string, approved: boolean): Promise<void> => {
    await apiClient.post(`/tasks/${taskId}/approval`, { approved });
  },
};
