/**
 * 领域层 - Session 会话实体定义
 */

export type SessionStatus = 'active' | 'archived';

export type SessionMessageRole = 'user' | 'assistant' | 'system' | 'tool_summary';

export type MessageStatus = 'completed' | 'streaming' | 'error';

export interface Session {
  id: string;
  agent_id: string;
  title: string;
  status: SessionStatus;
  message_count: number;
  last_message_preview: string;
  created_at: string;
  updated_at: string | null;
}

export interface SessionMessage {
  id: string;
  session_id: string;
  task_id: string | null;
  role: SessionMessageRole;
  content: string;
  tool_calls: ToolCallInfo[];
  tool_results: ToolResultInfo[];
  status: MessageStatus;
  error: string | null;
  cost: Record<string, unknown>;
  created_at: string;
  meta?: SessionMessageMeta;
}

export interface SessionMessageMeta {
  isSubAgent?: boolean;
  stepId?: number;
  title?: string;
}

export interface ToolCallInfo {
  name: string;
  id: string;
  args?: Record<string, unknown>;
  input?: Record<string, unknown>;
}

export interface ToolResultInfo {
  tool_name: string;
  id?: string;
  result: string;
  status: string;
  metadata?: Record<string, unknown>;
}

export interface CreateSessionRequest {
  title?: string;
}

export interface UpdateSessionRequest {
  title?: string;
  status?: SessionStatus;
}

export interface SendMessageRequest {
  content: string;
  model?: string;
  max_turns?: number;
  workspace?: string;
  skill_ids?: string[];
}

export interface SessionListResponse {
  data: Session[];
  total: number;
}

export interface SessionDetailResponse {
  session: Session;
  messages: SessionMessage[];
}

export interface SendMessageResponse {
  user_message: SessionMessage;
  task_id: string;
}
