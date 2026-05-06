/**
 * 领域层 - Skill 技能实体定义
 */

export interface Skill {
  id: string;
  name: string;
  description: string;
  content: string;
  file_path: string;
  trigger_keywords: string[];
  steps: SkillStep[];
  category: string;
  enabled: boolean;
  created_at: string;
  updated_at: string | null;
}

export interface SkillStep {
  name: string;
  description: string;
  tool_name: string | null;
}

export interface SkillListResponse {
  data: Skill[];
  total: number;
}

/** Skill 分类常量 */
export const SKILL_CATEGORIES: Record<string, string> = {
  general: '通用',
  development: '开发',
  analysis: '分析',
  writing: '写作',
  design: '设计',
};
