/**
 * 表现层 - 主应用组件
 */
import React from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AgentManagementPage } from './pages/AgentManagementPage';
import { AgentEditPage } from './pages/AgentEditPage';
import { AgentPage } from './pages/AgentPage';
import { AgentSessionPage } from './pages/AgentSessionPage';
import { SkillManagementPage } from './pages/SkillManagementPage';
import { AppSidebar } from './components/AppSidebar';

/** 带条件导航栏的布局：对话页面（全屏）不显示侧边栏 */
const AppLayout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const location = useLocation();
  // 对话页面使用全屏布局，不显示侧边栏
  const isFullscreen = location.pathname.includes('/chat');

  if (isFullscreen) {
    return <>{children}</>;
  }

  return (
    <div className="flex h-screen">
      <AppSidebar />
      <main className="flex-1 overflow-auto">{children}</main>
    </div>
  );
};

export const App: React.FC = () => {
  return (
    <BrowserRouter>
      <AppLayout>
        <Routes>
          <Route path="/" element={<Navigate to="/agents" replace />} />
          <Route path="/agents" element={<AgentManagementPage />} />
          <Route path="/agents/new" element={<AgentEditPage />} />
          <Route path="/agents/:id/edit" element={<AgentEditPage />} />
          <Route path="/agents/:id/chat" element={<AgentSessionPage />} />
          <Route path="/agent" element={<AgentPage />} />
          <Route path="/skills" element={<SkillManagementPage />} />
        </Routes>
      </AppLayout>
    </BrowserRouter>
  );
};
