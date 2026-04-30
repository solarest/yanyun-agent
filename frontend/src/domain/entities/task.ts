/**
 * 领域层 - 任务实体定义
 */

export type TaskStatus = 'idle' | 'running' | 'completed' | 'failed' | 'cancelled' | 'paused';

export type AgentPhase =
  | 'idle'
  | 'thinking'
  | 'tool_executing'
  | 'loop_correcting'
  | 'stuck_recovering'
  | 'context_compacting'
  | 'complete'
  | 'failed'
  | 'cancelled';

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
