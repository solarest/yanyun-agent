/**
 * 应用层 - Agent 管理服务 Hook
 */
import { useState, useCallback } from 'react';
import { agentApi } from '@infrastructure/api/agentApi';
import type {
  Agent,
  CreateAgentRequest,
  UpdateAgentRequest,
  UpdateAgentConfigRequest,
  AgentDefinitionConfig,
} from '@domain/entities/agent';

export const useAgentManagement = () => {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [currentAgent, setCurrentAgent] = useState<Agent | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [total, setTotal] = useState(0);

  const fetchAgents = useCallback(
    async (page = 1, pageSize = 20) => {
      setIsLoading(true);
      setError(null);
      try {
        const result = await agentApi.list({ page, pageSize });
        setAgents(result.data);
        setTotal(result.total);
      } catch (err) {
        setError(err instanceof Error ? err.message : '获取 Agent 列表失败');
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const fetchAgent = useCallback(async (id: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const agent = await agentApi.get(id);
      setCurrentAgent(agent);
      return agent;
    } catch (err) {
      setError(err instanceof Error ? err.message : '获取 Agent 详情失败');
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const createAgent = useCallback(async (data: CreateAgentRequest) => {
    setIsLoading(true);
    setError(null);
    try {
      const agent = await agentApi.create(data);
      setAgents((prev) => [agent, ...prev]);
      return agent;
    } catch (err) {
      setError(err instanceof Error ? err.message : '创建 Agent 失败');
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const updateAgent = useCallback(
    async (id: string, data: UpdateAgentRequest) => {
      setIsLoading(true);
      setError(null);
      try {
        const agent = await agentApi.update(id, data);
        setAgents((prev) => prev.map((a) => (a.id === id ? agent : a)));
        setCurrentAgent(agent);
        return agent;
      } catch (err) {
        setError(err instanceof Error ? err.message : '更新 Agent 失败');
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const deleteAgent = useCallback(async (id: string) => {
    setIsLoading(true);
    setError(null);
    try {
      await agentApi.delete(id);
      setAgents((prev) => prev.filter((a) => a.id !== id));
      if (currentAgent?.id === id) {
        setCurrentAgent(null);
      }
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除 Agent 失败');
      return false;
    } finally {
      setIsLoading(false);
    }
  }, [currentAgent]);

  const updateConfig = useCallback(
    async (id: string, data: UpdateAgentConfigRequest): Promise<AgentDefinitionConfig | null> => {
      setIsLoading(true);
      setError(null);
      try {
        const config = await agentApi.updateConfig(id, data);
        if (currentAgent && currentAgent.id === id) {
          setCurrentAgent({
            ...currentAgent,
            ...data,
            config_version: config.config_version,
          } as Agent);
        }
        return config;
      } catch (err) {
        setError(err instanceof Error ? err.message : '更新配置失败');
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    [currentAgent]
  );

  return {
    agents,
    currentAgent,
    isLoading,
    error,
    total,
    fetchAgents,
    fetchAgent,
    createAgent,
    updateAgent,
    deleteAgent,
    updateConfig,
    setCurrentAgent,
  };
};
