/**
 * 前端领域层 - Agent 实体类型定义
 */

/** Agent 完整实体 */
export interface Agent {
  id: string;
  name: string;
  description: string;
  vibes: string[];
  identity_md: string;
  soul_md: string;
  agents_md: string;
  bootstrap_md: string;
  memory_md: string;
  tools_md: string;
  user_md: string;
  config_version: number;
  created_at: string;
  updated_at: string | null;
}

/** Agent 配置文件响应 */
export interface AgentDefinitionConfig {
  identity_md: string;
  soul_md: string;
  agents_md: string;
  bootstrap_md: string;
  memory_md: string;
  tools_md: string;
  user_md: string;
  config_version: number;
}

/** 创建 Agent 请求 */
export interface CreateAgentRequest {
  name: string;
  description?: string;
  vibes?: string[];
  identity_md?: string;
  soul_md?: string;
  agents_md?: string;
  bootstrap_md?: string;
  memory_md?: string;
  tools_md?: string;
  user_md?: string;
}

/** 更新 Agent 请求 */
export interface UpdateAgentRequest {
  name?: string;
  description?: string;
  vibes?: string[];
  identity_md?: string;
  soul_md?: string;
  agents_md?: string;
  bootstrap_md?: string;
  memory_md?: string;
  tools_md?: string;
  user_md?: string;
}

/** 更新配置文件请求 */
export interface UpdateAgentConfigRequest {
  identity_md?: string;
  soul_md?: string;
  agents_md?: string;
  bootstrap_md?: string;
  memory_md?: string;
  tools_md?: string;
  user_md?: string;
}

/** Agent 列表响应 */
export interface AgentListResponse {
  data: Agent[];
  total: number;
}

/** 配置文件名称常量 */
export const CONFIG_FILE_LABELS: Record<string, string> = {
  identity_md: 'IDENTITY.md',
  soul_md: 'SOUL.md',
  agents_md: 'AGENTS.md',
  bootstrap_md: 'BOOTSTRAP.md',
  memory_md: 'MEMORY.md',
  tools_md: 'TOOLS.md',
  user_md: 'USER.md',
};

/** 配置文件描述 */
export const CONFIG_FILE_DESCRIPTIONS: Record<string, string> = {
  identity_md: '身份定义与系统边界约束',
  soul_md: '响应语气、行为特征及输出格式',
  agents_md: '调度规则与标准作业程序',
  bootstrap_md: '初始化序列与核心系统提示词',
  memory_md: '长期上下文数据与既定规则',
  tools_md: '工具授权注册表及调用参数',
  user_md: '用户画像数据与交互限制',
};
