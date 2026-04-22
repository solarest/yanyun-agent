/**
 * 前端领域层 - Repository 接口
 * 
 * 遵循依赖倒置原则:
 * - 领域层定义接口
 * - 基础设施层实现接口
 */
import { PingRequest, PingResponse } from '@application/dtos';

export interface PingRepository {
  ping(request: PingRequest): Promise<PingResponse>;
}
