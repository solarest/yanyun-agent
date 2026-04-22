/**
 * 应用层 - Ping 服务 Hook
 * 
 * 封装业务逻辑,管理状态
 */
import { useState } from 'react';
import { PingRepository } from '@domain/repositories';
import { PingApiRepository } from '@infrastructure/api/pingApi';
import { PingRequest, PingResponse } from '@application/dtos';

interface UsePingServiceResult {
  ping: (request?: PingRequest) => Promise<void>;
  isLoading: boolean;
  error: string | null;
  result: PingResponse | null;
}

const repository: PingRepository = new PingApiRepository();

export function usePingService(): UsePingServiceResult {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PingResponse | null>(null);

  const ping = async (request?: PingRequest) => {
    setIsLoading(true);
    setError(null);
    
    try {
      const response = await repository.ping(request ?? { message: 'ping' });
      setResult(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setIsLoading(false);
    }
  };

  return { ping, isLoading, error, result };
}
