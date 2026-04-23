/**
 * 领域层 - 任务实体定义
 */

export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';

export type AgentPhase = 'idle' | 'llm_call' | 'tool_execute' | 'loop_detect' | 'context_compact' | 'complete';

export interface AgentConfig {
  name: string;
  description: string;
  systemPrompt: string;
  provider: string;
  model: string;
  maxIterations: number;
}

export interface Task {
  id: string;
  agentName: string;
  userInput: string;
  status: TaskStatus;
  phase: AgentPhase;
  createdAt: string;
  updatedAt: string;
  output?: string;
  error?: string;
}

export interface CreateTaskRequest {
  agentName: string;
  userInput: string;
  config?: Partial<AgentConfig>;
}

export interface TaskListResponse {
  data: Task[];
  pagination: {
    page: number;
    pageSize: number;
    total: number;
    totalPages: number;
  };
}
