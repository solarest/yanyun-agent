/**
 * 领域层 - Session 会话实体定义
 */

export type SessionStatus = 'active' | 'archived';

export type SessionMessageRole = 'user' | 'assistant' | 'system' | 'tool_summary';

export type MessageStatus = 'completed' | 'streaming' | 'error';

/** 消息时间线片段类型 — 按事件实际发生顺序记录 */
export type SegmentType = 'thinking' | 'text' | 'tool';

/** 消息时间线片段 — 渲染时按 segments 数组顺序展示，保持工作流时间线 */
export interface MessageSegment {
  type: SegmentType;
  /** thinking/text: 内容文本；tool: 工具名称 */
  content?: string;
  /** 仅 tool 类型：工具参数 */
  toolInput?: Record<string, unknown>;
  /** 仅 tool 类型：工具结果 */
  toolResult?: string;
  /** 仅 tool 类型：工具执行状态 */
  toolStatus?: string;
  /** 仅 tool 类型：工具调用 ID */
  toolCallId?: string;
}

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
  thinking_content?: string;  // 深度思考内容
  has_thinking?: boolean;     // 是否有思考内容
  tool_calls: ToolCallInfo[];
  tool_results: ToolResultInfo[];
  /** 时间线片段 — 按实际事件发生顺序排列，用于时间线渲染 */
  segments?: MessageSegment[];
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

export interface ActiveTask {
  task_id: string;
  status: string;
  message: string;
  created_at: string;
}

export interface ActiveTasksResponse {
  tasks: ActiveTask[];
}
