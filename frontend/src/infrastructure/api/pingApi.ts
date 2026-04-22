/**
 * 基础设施层 - Ping API 实现
 * 
 * 实现领域层定义的 PingRepository 接口
 */
import { PingRepository } from '@domain/repositories';
import { PingRequest, PingResponse } from '@application/dtos';
import { apiClient } from './client';

export class PingApiRepository implements PingRepository {
  async ping(request: PingRequest): Promise<PingResponse> {
    const response = await apiClient.post<PingResponse>('/ping', request);
    return response.data;
  }
}
