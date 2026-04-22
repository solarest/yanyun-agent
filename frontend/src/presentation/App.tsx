/**
 * 表现层 - 主应用组件
 */
import React from 'react';
import { AgentPage } from './pages/AgentPage';

export const App: React.FC = () => {
  return (
    <div>
      <AgentPage />
    </div>
  );
};
