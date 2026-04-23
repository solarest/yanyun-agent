/**
 * 基础设施层 - LLM 配置 API 客户端
 */
import { apiClient } from './client';

/** 后端返回的原始格式（snake_case） */
interface LLMProviderInfoRaw {
  name: string;
  available_models: string[];
}

export interface LLMProviderInfo {
  name: string;
  availableModels: string[];
}

export const llmConfigApi = {
  /**
   * 获取可用的 LLM 提供商和模型列表
   */
  getProviders: async (): Promise<LLMProviderInfo[]> => {
    const response = await apiClient.get<LLMProviderInfoRaw[]>('/llm/providers');
    return response.data.map((p) => ({
      name: p.name,
      availableModels: p.available_models,
    }));
  },
};
