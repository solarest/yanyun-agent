/**
 * 表现层 - 全局左侧边栏导航
 *
 * 参考设计：左侧固定宽度侧边栏，包含主导航项（技能、专家套件等）
 */
import React from 'react';
import { Link, useLocation } from 'react-router-dom';

const NAV_ITEMS = [
  { path: '/skills', label: '技能', icon: SkillIcon },
  { path: '/agents', label: '我的Agent', icon: AgentIcon },
];

function SkillIcon() {
  return (
    <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M12 2L2 7l10 5 10-5-10-5z" />
      <path d="M2 17l10 5 10-5" />
      <path d="M2 12l10 5 10-5" />
    </svg>
  );
}

function AgentIcon() {
  return (
    <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
    </svg>
  );
}

export const AppSidebar: React.FC = () => {
  const location = useLocation();

  const isActive = (path: string) => location.pathname.startsWith(path);

  return (
    <aside className="flex h-screen w-60 flex-shrink-0 flex-col border-r bg-background">
      {/* Logo */}
      <div className="flex items-center gap-2 border-b px-4 py-3">
        <img src="/wordlight-logo.png" alt="WordLight" className="h-7 w-7 rounded" />
        <span className="text-lg font-bold">WordLight</span>
      </div>

      {/* 主导航 */}
      <nav className="flex-1 space-y-1 px-3 py-3">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          return (
            <Link
              key={item.path}
              to={item.path}
              className={`flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                isActive(item.path)
                  ? 'bg-primary/10 text-primary'
                  : 'text-muted-foreground hover:bg-secondary hover:text-foreground'
              }`}
            >
              <Icon />
              <span className="flex-1">{item.label}</span>
            </Link>
          );
        })}
      </nav>

      {/* 底部信息 */}
      <div className="border-t px-4 py-3">
        <p className="text-xs text-muted-foreground">WordLight Agent</p>
      </div>
    </aside>
  );
};
