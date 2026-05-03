/**
 * 应用层 - Session 管理服务 Hook
 */
import { useState, useCallback } from 'react';
import { sessionApi } from '../../infrastructure/api/sessionApi';
import type {
  Session,
  SessionMessage,
  UpdateSessionRequest,
} from '../../domain/entities/session';

export const useSessionService = (agentId: string) => {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [currentSession, setCurrentSession] = useState<Session | null>(null);
  const [messages, setMessages] = useState<SessionMessage[]>([]);

  const fetchSessions = useCallback(async (page = 1, pageSize = 20) => {
    if (!agentId) return;
    setIsLoading(true);
    setError(null);
    try {
      const response = await sessionApi.listSessions(agentId, page, pageSize);
      setSessions(response.data);
      return response;
    } catch (err: unknown) {
      const errorMessage = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail || '获取会话列表失败';
      setError(errorMessage);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, [agentId]);

  const createSession = useCallback(async (title?: string) => {
    if (!agentId) return;
    setIsLoading(true);
    setError(null);
    try {
      const session = await sessionApi.createSession(agentId, { title });
      setSessions(prev => [session, ...prev]);
      setCurrentSession(session);
      setMessages([]);
      return session;
    } catch (err: unknown) {
      const errorMessage = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail || '创建会话失败';
      setError(errorMessage);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, [agentId]);

  const selectSession = useCallback(async (sessionId: string) => {
    if (!agentId) return;
    setIsLoading(true);
    setError(null);
    try {
      const detail = await sessionApi.getSessionDetail(agentId, sessionId);
      setCurrentSession(detail.session);
      setMessages(detail.messages);
      return detail;
    } catch (err: unknown) {
      const errorMessage = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail || '获取会话详情失败';
      setError(errorMessage);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, [agentId]);

  const updateSession = useCallback(async (sessionId: string, request: UpdateSessionRequest) => {
    if (!agentId) return;
    setIsLoading(true);
    setError(null);
    try {
      const updated = await sessionApi.updateSession(agentId, sessionId, request);
      setSessions(prev => prev.map(s => s.id === sessionId ? updated : s));
      if (currentSession?.id === sessionId) {
        setCurrentSession(updated);
      }
      return updated;
    } catch (err: unknown) {
      const errorMessage = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail || '更新会话失败';
      setError(errorMessage);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, [agentId, currentSession]);

  const deleteSession = useCallback(async (sessionId: string) => {
    if (!agentId) return;
    setIsLoading(true);
    setError(null);
    try {
      await sessionApi.deleteSession(agentId, sessionId);
      setSessions(prev => prev.filter(s => s.id !== sessionId));
      if (currentSession?.id === sessionId) {
        setCurrentSession(null);
        setMessages([]);
      }
    } catch (err: unknown) {
      const errorMessage = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail || '删除会话失败';
      setError(errorMessage);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, [agentId, currentSession]);

  /**
   * 向消息列表追加消息（供 useChat 调用）
   */
  const appendMessage = useCallback((msg: SessionMessage) => {
    setMessages(prev => [...prev, msg]);
  }, []);

  const upsertMessage = useCallback((msg: SessionMessage) => {
    setMessages(prev => {
      const index = prev.findIndex(item => item.id === msg.id);
      if (index === -1) {
        return [...prev, msg];
      }

      const next = [...prev];
      next[index] = msg;
      return next;
    });
  }, []);

  const updateMessageById = useCallback((
    messageId: string,
    updater: (msg: SessionMessage) => SessionMessage,
  ) => {
    setMessages(prev => {
      const index = prev.findIndex(item => item.id === messageId);
      if (index === -1) return prev;

      const next = [...prev];
      next[index] = updater(next[index]);
      return next;
    });
  }, []);

  /**
   * 更新消息列表中的最后一条 assistant 消息
   */
  const updateLastAssistantMessage = useCallback((updater: (msg: SessionMessage) => SessionMessage) => {
    setMessages(prev => {
      const idx = prev.length - 1;
      if (idx >= 0 && prev[idx].role === 'assistant') {
        const updated = [...prev];
        updated[idx] = updater(updated[idx]);
        return updated;
      }
      return prev;
    });
  }, []);

  return {
    isLoading,
    error,
    sessions,
    currentSession,
    messages,
    fetchSessions,
    createSession,
    selectSession,
    updateSession,
    deleteSession,
    setCurrentSession,
    appendMessage,
    upsertMessage,
    updateMessageById,
    updateLastAssistantMessage,
  };
};
