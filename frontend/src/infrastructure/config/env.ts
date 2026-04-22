/**
 * 基础设施层 - 环境配置
 */

export const config = {
  apiUrl: import.meta.env.VITE_API_URL || '/api',
  appTitle: 'DDD Frontend',
} as const;
