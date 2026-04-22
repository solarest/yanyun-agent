/**
 * 前端领域层 - DTO 类型定义
 * 
 * 与后端 DTO 保持对应,确保类型安全
 */

export interface PingRequest {
  message?: string;
}

export interface PingResponse {
  status: string;
  timestamp: string;
  message: string;
  server: string;
}
