/**
 * 表现层 - 主应用组件
 */
import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AgentManagementPage } from './pages/AgentManagementPage';
import { AgentEditPage } from './pages/AgentEditPage';
import { AgentPage } from './pages/AgentPage';
import { AgentSessionPage } from './pages/AgentSessionPage';

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/agents" replace />} />
        <Route path="/agents" element={<AgentManagementPage />} />
        <Route path="/agents/new" element={<AgentEditPage />} />
        <Route path="/agents/:id/edit" element={<AgentEditPage />} />
        <Route path="/agents/:id/chat" element={<AgentSessionPage />} />
        <Route path="/agent" element={<AgentPage />} />
      </Routes>
    </BrowserRouter>
  );
};
