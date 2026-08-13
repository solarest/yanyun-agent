/**
 * 表现层 - 主应用组件
 *
 * 路由按页面 React.lazy 代码分割：react-markdown 等重依赖
 * 只进入用到它们的页面 chunk（如会话页、团队执行页）。
 */
import React, { Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { AppSidebar } from './components/AppSidebar';

/** 命名导出的页面 → React.lazy 组件 */
function lazyPage<T extends React.ComponentType>(
  loader: () => Promise<Record<string, T>>,
  name: string,
) {
  return React.lazy(() => loader().then((m) => ({ default: m[name] })));
}

const AgentManagementPage = lazyPage(
  () => import('./pages/AgentManagementPage'),
  'AgentManagementPage',
);
const AgentEditPage = lazyPage(() => import('./pages/AgentEditPage'), 'AgentEditPage');
const AgentPage = lazyPage(() => import('./pages/AgentPage'), 'AgentPage');
const AgentSessionPage = lazyPage(
  () => import('./pages/AgentSessionPage'),
  'AgentSessionPage',
);
const SkillManagementPage = lazyPage(
  () => import('./pages/SkillManagementPage'),
  'SkillManagementPage',
);
const TeamManagementPage = lazyPage(
  () => import('./pages/TeamManagementPage'),
  'TeamManagementPage',
);
const TeamCreatePage = lazyPage(() => import('./pages/TeamCreatePage'), 'TeamCreatePage');
const TeamDetailPage = lazyPage(() => import('./pages/TeamDetailPage'), 'TeamDetailPage');
const TeamExecutionPage = lazyPage(
  () => import('./pages/TeamExecutionPage'),
  'TeamExecutionPage',
);

/** 懒加载 fallback */
const PageFallback: React.FC = () => (
  <div className="flex h-full min-h-[40vh] items-center justify-center">
    <div className="text-sm text-muted-foreground">
      <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-primary mr-2" />
      加载中...
    </div>
  </div>
);

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
        <Suspense fallback={<PageFallback />}>
          <Routes>
            <Route path="/" element={<Navigate to="/agents" replace />} />
            <Route path="/agents" element={<AgentManagementPage />} />
            <Route path="/agents/new" element={<AgentEditPage />} />
            <Route path="/agents/:id/edit" element={<AgentEditPage />} />
            <Route path="/agents/:id/chat" element={<AgentSessionPage />} />
            <Route path="/agent" element={<AgentPage />} />
            <Route path="/skills" element={<SkillManagementPage />} />
            {/* Team 路由 */}
            <Route path="/teams" element={<TeamManagementPage />} />
            <Route path="/teams/new" element={<TeamCreatePage />} />
            <Route path="/teams/:id" element={<TeamDetailPage />} />
            <Route path="/teams/:id/execute" element={<TeamExecutionPage />} />
          </Routes>
        </Suspense>
      </AppLayout>
    </BrowserRouter>
  );
};
