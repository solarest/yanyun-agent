/**
 * 表现层 - 对话中的 Skill 选择组件
 *
 * 设计：消息输入区左侧 "+" 按钮，点击后弹出菜单选择 "技能"，
 * 然后展示可用技能列表供用户选择/取消。底部有 "管理技能" 入口。
 */
import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { skillApi } from '@infrastructure/api/skillApi';
import type { Skill } from '@domain/entities/skill';

interface SkillSelectorProps {
  selectedSkillIds: string[];
  onSelectionChange: (skillIds: string[]) => void;
}

export const SkillSelector: React.FC<SkillSelectorProps> = ({
  selectedSkillIds,
  onSelectionChange,
}) => {
  const navigate = useNavigate();
  const [skills, setSkills] = useState<Skill[]>([]);
  const [menuOpen, setMenuOpen] = useState(false);
  const [skillListOpen, setSkillListOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // 加载启用的 Skills
  useEffect(() => {
    const loadSkills = async () => {
      try {
        const result = await skillApi.listEnabled();
        setSkills(result.data);
      } catch {
        // 静默处理错误
      }
    };
    loadSkills();
  }, []);

  // 点击外部关闭弹出
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
        setSkillListOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleToggle = useCallback(
    (skillId: string) => {
      if (selectedSkillIds.includes(skillId)) {
        onSelectionChange(selectedSkillIds.filter((id) => id !== skillId));
      } else {
        onSelectionChange([...selectedSkillIds, skillId]);
      }
    },
    [selectedSkillIds, onSelectionChange],
  );

  const handlePlusClick = () => {
    if (skillListOpen) {
      setSkillListOpen(false);
      setMenuOpen(false);
    } else if (menuOpen) {
      setMenuOpen(false);
    } else {
      setMenuOpen(true);
    }
  };

  const handleSkillMenuClick = () => {
    setMenuOpen(false);
    setSkillListOpen(true);
  };

  const handleManageSkills = () => {
    setSkillListOpen(false);
    setMenuOpen(false);
    navigate('/skills');
  };

  return (
    <div ref={containerRef} className="relative">
      {/* "+" 按钮 */}
      <button
        type="button"
        onClick={handlePlusClick}
        className={`flex h-8 w-8 items-center justify-center rounded-full transition-colors ${
          selectedSkillIds.length > 0
            ? 'bg-primary/10 text-primary'
            : 'text-muted-foreground hover:bg-secondary hover:text-foreground'
        }`}
        title="添加技能"
      >
        <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <line x1="12" y1="5" x2="12" y2="19" />
          <line x1="5" y1="12" x2="19" y2="12" />
        </svg>
        {selectedSkillIds.length > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-primary text-[9px] font-bold text-primary-foreground">
            {selectedSkillIds.length}
          </span>
        )}
      </button>

      {/* 第一层菜单：功能选项 */}
      {menuOpen && (
        <div className="absolute bottom-full left-0 mb-2 w-40 rounded-lg border bg-popover p-1 shadow-lg">
          <button
            type="button"
            onClick={handleSkillMenuClick}
            className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-foreground hover:bg-secondary"
          >
            <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 2L2 7l10 5 10-5-10-5z" />
              <path d="M2 17l10 5 10-5" />
              <path d="M2 12l10 5 10-5" />
            </svg>
            技能
            {selectedSkillIds.length > 0 && (
              <span className="ml-auto rounded-full bg-primary/10 px-1.5 text-xs text-primary">
                {selectedSkillIds.length}
              </span>
            )}
          </button>
        </div>
      )}

      {/* 第二层：技能列表 */}
      {skillListOpen && (
        <div className="absolute bottom-full left-0 mb-2 z-50 w-72 rounded-lg border bg-popover shadow-lg">
          <div className="border-b px-3 py-2">
            <h4 className="text-sm font-medium">选择技能</h4>
          </div>
          <div className="max-h-64 overflow-y-auto p-1">
            {skills.length === 0 ? (
              <p className="px-3 py-4 text-center text-sm text-muted-foreground">
                暂无可用技能
              </p>
            ) : (
              <div className="space-y-1">
                {skills.map((skill) => (
                  <button
                    key={skill.id}
                    type="button"
                    onClick={() => handleToggle(skill.id)}
                    className={`flex w-full items-start gap-2 rounded-md px-3 py-2.5 text-left transition-colors ${
                      selectedSkillIds.includes(skill.id)
                        ? 'bg-primary/10'
                        : 'hover:bg-secondary'
                    }`}
                  >
                    <span
                      className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border ${
                        selectedSkillIds.includes(skill.id)
                          ? 'border-primary bg-primary text-primary-foreground'
                          : 'border-muted-foreground/30'
                      }`}
                    >
                      {selectedSkillIds.includes(skill.id) && (
                        <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                          <polyline points="20 6 9 17 4 12" />
                        </svg>
                      )}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium leading-tight">{skill.name}</p>
                      <p className="mt-0.5 text-xs leading-tight text-muted-foreground">
                        {skill.description}
                      </p>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
          <div className="border-t px-3 py-2">
            <button
              type="button"
              onClick={handleManageSkills}
              className="text-xs text-primary hover:underline"
            >
              管理技能
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
