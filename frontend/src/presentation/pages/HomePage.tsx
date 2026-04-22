/**
 * 表现层 - 首页
 */
import React from 'react';
import { usePingService } from '@application/services/pingService';
import { PingButton } from '@presentation/components/PingButton';

export const HomePage: React.FC = () => {
  const { ping, isLoading, error, result } = usePingService();

  return (
    <div style={{ padding: '20px', maxWidth: '800px', margin: '0 auto' }}>
      <h1>DDD Python + TypeScript Scaffold</h1>
      <p>这是一个 DDD 架构的全栈脚手架项目</p>
      
      <div style={{ margin: '30px 0' }}>
        <PingButton onClick={() => ping()} isLoading={isLoading} />
      </div>

      {error && (
        <div style={{ color: 'red', padding: '10px', backgroundColor: '#ffe0e0', borderRadius: '4px' }}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {result && (
        <div style={{ padding: '15px', backgroundColor: '#f5f5f5', borderRadius: '4px', marginTop: '20px' }}>
          <h3>Response:</h3>
          <pre style={{ backgroundColor: '#fff', padding: '10px', borderRadius: '4px' }}>
            {JSON.stringify(result, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
};
