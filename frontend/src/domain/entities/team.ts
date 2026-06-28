/**
 * 领域层 - Team 实体类型定义
 */

export interface Team {
  id: string;
  name: string;
  description: string;
  leader_id: string;
  goal: string;
  status: 'idle' | 'planning' | 'executing' | 'completed' | 'failed';
  config: Record<string, unknown>;
  member_count: number;
  created_at: string;
  updated_at: string | null;
}

export interface TeamMember {
  id: string;
  agent_id: string;
  agent_name?: string;
  role: 'leader' | 'member';
  status: 'idle' | 'busy' | 'done';
  joined_at: string;
}

export interface TeamDetail extends Team {
  members: TeamMember[];
}

export interface TeamListResponse {
  teams: Team[];
  total: number;
  page: number;
  page_size: number;
}

export interface CreateTeamRequest {
  name: string;
  description?: string;
  leader_id: string;
  member_ids: string[];
}

export interface UpdateTeamRequest {
  name?: string;
  description?: string;
  leader_id?: string;
  member_ids?: string[];
}

export interface ExecuteTeamRequest {
  goal: string;
  model?: string;
  max_turns?: number;
  workspace?: string;
  session_id?: string;
}

export interface ExecuteTeamResponse {
  team_id: string;
  execution_id: string;
  session_id: string;
  workspace: string;
  status: string;
  message: string;
}
