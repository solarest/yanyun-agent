/**
 * 应用层 - 任务服务 Hook
 */
import { useState, useCallback } from 'react';
import { taskApi } from '../../infrastructure/api/taskApi';
import type { CreateTaskRequest, Task, TaskListResponse } from '../../domain/entities/task';

export const useTaskService = () => {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [currentTask, setCurrentTask] = useState<Task | null>(null);

  const createTask = useCallback(async (request: CreateTaskRequest) => {
    setIsLoading(true);
    setError(null);
    try {
      const task = await taskApi.createTask(request);
      setCurrentTask(task);
      setTasks(prev => [task, ...prev]);
      return task;
    } catch (err: any) {
      const errorMessage = err.response?.data?.detail || '创建任务失败';
      setError(errorMessage);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const fetchTasks = useCallback(async (page = 1, pageSize = 20) => {
    setIsLoading(true);
    setError(null);
    try {
      const response: TaskListResponse = await taskApi.listTasks(page, pageSize);
      setTasks(response.data);
      return response;
    } catch (err: any) {
      const errorMessage = err.response?.data?.detail || '获取任务列表失败';
      setError(errorMessage);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const fetchTask = useCallback(async (taskId: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const task = await taskApi.getTask(taskId);
      setCurrentTask(task);
      return task;
    } catch (err: any) {
      const errorMessage = err.response?.data?.detail || '获取任务详情失败';
      setError(errorMessage);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const cancelTask = useCallback(async (taskId: string) => {
    setIsLoading(true);
    setError(null);
    try {
      await taskApi.cancelTask(taskId);
      setTasks(prev => prev.map(t => t.id === taskId ? { ...t, status: 'cancelled' } : t));
      if (currentTask?.id === taskId) {
        setCurrentTask(prev => prev ? { ...prev, status: 'cancelled' } : null);
      }
    } catch (err: any) {
      const errorMessage = err.response?.data?.detail || '取消任务失败';
      setError(errorMessage);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, [currentTask]);

  return {
    isLoading,
    error,
    tasks,
    currentTask,
    createTask,
    fetchTasks,
    fetchTask,
    cancelTask,
    setCurrentTask,
  };
};
