/**
 * 应用层 - Team 管理服务 Hook
 */
import { useState, useCallback } from 'react';
import { teamApi } from '@infrastructure/api/teamApi';
import type {
  Team,
  TeamDetail,
  CreateTeamRequest,
  UpdateTeamRequest,
  ExecuteTeamResponse,
} from '@domain/entities/team';

/** 从捕获的错误中提取可读消息（兼容 axios 错误和普通 Error） */
function extractErrorMessage(err: unknown, fallback: string): string {
  if (err && typeof err === 'object' && 'response' in err) {
    const axiosErr = err as { response?: { data?: { detail?: string } } };
    return axiosErr.response?.data?.detail || fallback;
  }
  return err instanceof Error ? err.message : fallback;
}

export const useTeamManagement = () => {
  const [teams, setTeams] = useState<Team[]>([]);
  const [currentTeam, setCurrentTeam] = useState<TeamDetail | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [total, setTotal] = useState(0);

  const fetchTeams = useCallback(async (page = 1, pageSize = 20) => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await teamApi.list({ page, pageSize });
      setTeams(result.teams);
      setTotal(result.total);
    } catch (err) {
      setError(extractErrorMessage(err, '获取 Team 列表失败'));
    } finally {
      setIsLoading(false);
    }
  }, []);

  const fetchTeam = useCallback(async (id: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const team = await teamApi.get(id);
      setCurrentTeam(team);
      return team;
    } catch (err) {
      setError(extractErrorMessage(err, '获取 Team 详情失败'));
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const createTeam = useCallback(async (data: CreateTeamRequest) => {
    setIsLoading(true);
    setError(null);
    try {
      const team = await teamApi.create(data);
      setTeams((prev) => [team, ...prev]);
      return team;
    } catch (err) {
      setError(extractErrorMessage(err, '创建 Team 失败'));
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const updateTeam = useCallback(
    async (id: string, data: UpdateTeamRequest) => {
      setIsLoading(true);
      setError(null);
      try {
        const team = await teamApi.update(id, data);
        setTeams((prev) => prev.map((t) => (t.id === id ? team : t)));
        return team;
      } catch (err) {
        setError(extractErrorMessage(err, '更新 Team 失败'));
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const deleteTeam = useCallback(async (id: string) => {
    setIsLoading(true);
    setError(null);
    try {
      await teamApi.delete(id);
      setTeams((prev) => prev.filter((t) => t.id !== id));
      if (currentTeam?.id === id) {
        setCurrentTeam(null);
      }
      return true;
    } catch (err) {
      setError(extractErrorMessage(err, '删除 Team 失败'));
      return false;
    } finally {
      setIsLoading(false);
    }
  }, [currentTeam]);

  const executeTeam = useCallback(
    async (teamId: string, goal: string, model?: string, sessionId?: string): Promise<ExecuteTeamResponse | null> => {
      setIsLoading(true);
      setError(null);
      try {
        const result = await teamApi.execute(teamId, { goal, model, session_id: sessionId });
        return result;
      } catch (err) {
        setError(extractErrorMessage(err, '执行 Team 失败'));
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  return {
    teams,
    currentTeam,
    isLoading,
    error,
    total,
    fetchTeams,
    fetchTeam,
    createTeam,
    updateTeam,
    deleteTeam,
    executeTeam,
    setCurrentTeam,
  };
};
