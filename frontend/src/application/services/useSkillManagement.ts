/**
 * 应用层 - Skill 管理服务 Hook（ZIP 上传模式）
 */
import { useState, useCallback } from 'react';
import { skillApi } from '@infrastructure/api/skillApi';
import type { Skill } from '@domain/entities/skill';

export const useSkillManagement = () => {
  const [skills, setSkills] = useState<Skill[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [total, setTotal] = useState(0);

  const fetchSkills = useCallback(
    async (params?: { page?: number; pageSize?: number; category?: string; enabled?: boolean }) => {
      setIsLoading(true);
      setError(null);
      try {
        const result = await skillApi.list(params);
        setSkills(result.data);
        setTotal(result.total);
      } catch (err) {
        setError(err instanceof Error ? err.message : '获取 Skill 列表失败');
      } finally {
        setIsLoading(false);
      }
    },
    [],
  );

  const uploadSkill = useCallback(async (file: File) => {
    setIsLoading(true);
    setError(null);
    try {
      const skill = await skillApi.upload(file);
      setSkills((prev) => [skill, ...prev]);
      setTotal((prev) => prev + 1);
      return skill;
    } catch (err: unknown) {
      const msg = extractErrorMessage(err, '上传 Skill 失败');
      setError(msg);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const reuploadSkill = useCallback(async (id: string, file: File) => {
    setIsLoading(true);
    setError(null);
    try {
      const skill = await skillApi.reupload(id, file);
      setSkills((prev) => prev.map((s) => (s.id === id ? skill : s)));
      return skill;
    } catch (err: unknown) {
      const msg = extractErrorMessage(err, '重新上传 Skill 失败');
      setError(msg);
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const deleteSkill = useCallback(async (id: string) => {
    setIsLoading(true);
    setError(null);
    try {
      await skillApi.delete(id);
      setSkills((prev) => prev.filter((s) => s.id !== id));
      setTotal((prev) => prev - 1);
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除 Skill 失败');
      return false;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const toggleSkill = useCallback(async (id: string) => {
    setError(null);
    try {
      const skill = await skillApi.toggle(id);
      setSkills((prev) => prev.map((s) => (s.id === id ? skill : s)));
      return skill;
    } catch (err) {
      setError(err instanceof Error ? err.message : '切换 Skill 状态失败');
      return null;
    }
  }, []);

  return {
    skills,
    isLoading,
    error,
    total,
    fetchSkills,
    uploadSkill,
    reuploadSkill,
    deleteSkill,
    toggleSkill,
  };
};

/** 从 Axios 错误中提取后端返回的 message */
function extractErrorMessage(err: unknown, fallback: string): string {
  if (err && typeof err === 'object' && 'response' in err) {
    const resp = (err as { response?: { data?: { error?: { message?: string } } } }).response;
    if (resp?.data?.error?.message) {
      return resp.data.error.message;
    }
  }
  if (err instanceof Error) return err.message;
  return fallback;
}
