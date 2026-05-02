/**
 * 基础设施层 - Agent API 客户端
 */
import { apiClient } from './client';
import type {
  Agent,
  AgentDefinitionConfig,
  AgentListResponse,
  CreateAgentRequest,
  UpdateAgentRequest,
  UpdateAgentConfigRequest,
} from '@domain/entities/agent';

export interface ToolDef {
  name: string;
  description: string;
  category: string;
  parameters: Array<{
    name: string;
    type: string;
    description: string;
    required: boolean;
    enum?: any[];
  }>;
  returns: string;
}

export interface ToolListResponse {
  tools: ToolDef[];
  total: number;
}

export const agentApi = {
  /** 获取 Agent 列表 */
  list: async (params?: {
    page?: number;
    pageSize?: number;
  }): Promise<AgentListResponse> => {
    const response = await apiClient.get('/agents', {
      params: {
        page: params?.page ?? 1,
        page_size: params?.pageSize ?? 20,
      },
    });
    return response.data;
  },

  /** 获取 Agent 详情 */
  get: async (id: string): Promise<Agent> => {
    const response = await apiClient.get(`/agents/${id}`);
    return response.data;
  },

  /** 创建 Agent */
  create: async (data: CreateAgentRequest): Promise<Agent> => {
    const response = await apiClient.post('/agents', data);
    return response.data;
  },

  /** 更新 Agent */
  update: async (id: string, data: UpdateAgentRequest): Promise<Agent> => {
    const response = await apiClient.put(`/agents/${id}`, data);
    return response.data;
  },

  /** 删除 Agent */
  delete: async (id: string): Promise<void> => {
    await apiClient.delete(`/agents/${id}`);
  },

  /** 获取 Agent 配置文件 */
  getConfig: async (id: string): Promise<AgentDefinitionConfig> => {
    const response = await apiClient.get(`/agents/${id}/config`);
    return response.data;
  },

  /** 更新 Agent 配置文件 */
  updateConfig: async (
    id: string,
    data: UpdateAgentConfigRequest
  ): Promise<AgentDefinitionConfig> => {
    const response = await apiClient.put(`/agents/${id}/config`, data);
    return response.data;
  },

  /** 获取已注册工具列表 */
  listTools: async (category?: string): Promise<ToolListResponse> => {
    const response = await apiClient.get('/agents/tools', {
      params: category ? { category } : {},
    });
    return response.data;
  },
};
