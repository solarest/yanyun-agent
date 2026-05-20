/**
 * 表现层 - Skill 管理列表页（ZIP 上传模式）
 *
 * 路由: /skills
 */
import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useSkillManagement } from '@application/services/useSkillManagement';
import { SKILL_CATEGORIES } from '@domain/entities/skill';
import type { Skill } from '@domain/entities/skill';

export const SkillManagementPage: React.FC = () => {
  const { skills, isLoading, error, total, fetchSkills, uploadSkill, reuploadSkill, deleteSkill, toggleSkill } =
    useSkillManagement();
  const [deleteTarget, setDeleteTarget] = useState<Skill | null>(null);
  const [reuploadTarget, setReuploadTarget] = useState<Skill | null>(null);
  const [activeCategory, setActiveCategory] = useState<string | undefined>(undefined);
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [uploading, setUploading] = useState(false);
  const uploadInputRef = useRef<HTMLInputElement>(null);
  const reuploadInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetchSkills({ category: activeCategory });
  }, [fetchSkills, activeCategory]);

  const handleUpload = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      setUploading(true);
      const result = await uploadSkill(file);
      setUploading(false);
      if (result) {
        setShowUploadModal(false);
      }
      // 重置 input
      if (uploadInputRef.current) {
        uploadInputRef.current.value = '';
      }
    },
    [uploadSkill],
  );

  const handleReupload = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file || !reuploadTarget) return;
      setUploading(true);
      await reuploadSkill(reuploadTarget.id, file);
      setUploading(false);
      setReuploadTarget(null);
      if (reuploadInputRef.current) {
        reuploadInputRef.current.value = '';
      }
    },
    [reuploadSkill, reuploadTarget],
  );

  const handleDelete = useCallback(async () => {
    if (!deleteTarget) return;
    const success = await deleteSkill(deleteTarget.id);
    if (success) {
      setDeleteTarget(null);
    }
  }, [deleteTarget, deleteSkill]);

  const handleToggle = useCallback(
    async (id: string) => {
      await toggleSkill(id);
    },
    [toggleSkill],
  );

  return (
    <div className="mx-auto max-w-6xl p-6">
      {/* 头部 */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">技能管理</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            管理你的 AI 技能，增强对话能力
          </p>
        </div>
        <button
          onClick={() => setShowUploadModal(true)}
          className="inline-flex items-center rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          + 上传技能
        </button>
      </div>

      {/* 分类筛选 */}
      <div className="mb-4 flex gap-2">
        <button
          onClick={() => setActiveCategory(undefined)}
          className={`rounded-full px-3 py-1 text-sm ${
            !activeCategory
              ? 'bg-primary text-primary-foreground'
              : 'bg-secondary text-secondary-foreground hover:bg-secondary/80'
          }`}
        >
          全部 ({total})
        </button>
        {Object.entries(SKILL_CATEGORIES).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setActiveCategory(key)}
            className={`rounded-full px-3 py-1 text-sm ${
              activeCategory === key
                ? 'bg-primary text-primary-foreground'
                : 'bg-secondary text-secondary-foreground hover:bg-secondary/80'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* 错误提示 */}
      {error && (
        <div className="mb-4 rounded-lg border border-destructive bg-destructive/10 p-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {/* 加载状态 */}
      {isLoading && skills.length === 0 && (
        <div className="flex items-center justify-center py-20">
          <p className="text-muted-foreground">加载中...</p>
        </div>
      )}

      {/* 空状态 */}
      {!isLoading && skills.length === 0 && (
        <div className="flex flex-col items-center justify-center py-20">
          <p className="mb-4 text-lg text-muted-foreground">暂无技能</p>
          <button
            onClick={() => setShowUploadModal(true)}
            className="inline-flex items-center rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          >
            上传第一个技能
          </button>
        </div>
      )}

      {/* Skill 卡片网格 */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {skills.map((skill) => (
          <div
            key={skill.id}
            className={`group rounded-xl border bg-card p-5 transition-shadow hover:shadow-md ${
              !skill.enabled ? 'opacity-60' : ''
            }`}
          >
            {/* 头部 */}
            <div className="mb-3 flex items-start justify-between">
              <div className="min-w-0 flex-1">
                <h3 className="truncate font-semibold">{skill.name}</h3>
                <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">
                  {skill.description}
                </p>
              </div>
              {/* 启用开关 */}
              <button
                onClick={() => handleToggle(skill.id)}
                className={`ml-2 flex h-6 w-10 flex-shrink-0 items-center rounded-full px-0.5 transition-colors ${
                  skill.enabled ? 'bg-primary' : 'bg-muted'
                }`}
              >
                <span
                  className={`h-5 w-5 rounded-full bg-white shadow-sm transition-transform ${
                    skill.enabled ? 'translate-x-4' : 'translate-x-0'
                  }`}
                />
              </button>
            </div>

            {/* 分类与关键词 */}
            <div className="mb-3 flex flex-wrap gap-1">
              <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs text-blue-700">
                {SKILL_CATEGORIES[skill.category] || skill.category}
              </span>
              {skill.trigger_keywords.slice(0, 3).map((kw) => (
                <span
                  key={kw}
                  className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600"
                >
                  {kw}
                </span>
              ))}
            </div>

            {/* 内容预览 */}
            {skill.content && (
              <p className="mb-3 line-clamp-2 text-xs text-muted-foreground">
                {skill.content.slice(0, 100)}
              </p>
            )}

            {/* 操作按钮 */}
            <div className="flex items-center justify-between border-t pt-3">
              <span className="text-xs text-muted-foreground">
                {new Date(skill.created_at).toLocaleDateString()}
              </span>
              <div className="flex gap-2">
                <button
                  className="rounded-md bg-secondary px-3 py-1 text-xs text-secondary-foreground hover:bg-secondary/80"
                  onClick={() => setReuploadTarget(skill)}
                >
                  重新上传
                </button>
                <button
                  className="rounded-md bg-secondary px-3 py-1 text-xs text-destructive hover:bg-destructive/10"
                  onClick={() => setDeleteTarget(skill)}
                >
                  删除
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* 上传弹窗 */}
      {showUploadModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-md rounded-xl bg-card p-6 shadow-xl">
            <h3 className="mb-2 text-lg font-semibold">上传技能</h3>
            <p className="mb-4 text-sm text-muted-foreground">
              选择一个 ZIP 文件上传。ZIP 根目录必须包含 SKILL.md 文件。
            </p>
            <div className="mb-4 rounded-lg border-2 border-dashed border-muted-foreground/25 p-8 text-center">
              <p className="mb-2 text-sm text-muted-foreground">
                {uploading ? '上传中...' : '点击选择 ZIP 文件'}
              </p>
              <input
                ref={uploadInputRef}
                type="file"
                accept=".zip,application/zip"
                onChange={handleUpload}
                disabled={uploading}
                className="absolute inset-0 cursor-pointer opacity-0"
                style={{ position: 'relative' }}
              />
            </div>
            {error && (
              <p className="mb-4 text-sm text-destructive">{error}</p>
            )}
            <div className="flex justify-end">
              <button
                className="rounded-md bg-secondary px-4 py-2 text-sm text-secondary-foreground hover:bg-secondary/80"
                onClick={() => setShowUploadModal(false)}
                disabled={uploading}
              >
                取消
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 重新上传弹窗 */}
      {reuploadTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-md rounded-xl bg-card p-6 shadow-xl">
            <h3 className="mb-2 text-lg font-semibold">重新上传</h3>
            <p className="mb-4 text-sm text-muted-foreground">
              为 &quot;{reuploadTarget.name}&quot; 选择新的 ZIP 文件上传，将替换现有内容。
            </p>
            <div className="mb-4 rounded-lg border-2 border-dashed border-muted-foreground/25 p-8 text-center">
              <p className="mb-2 text-sm text-muted-foreground">
                {uploading ? '上传中...' : '点击选择 ZIP 文件'}
              </p>
              <input
                ref={reuploadInputRef}
                type="file"
                accept=".zip,application/zip"
                onChange={handleReupload}
                disabled={uploading}
                className="absolute inset-0 cursor-pointer opacity-0"
                style={{ position: 'relative' }}
              />
            </div>
            {error && (
              <p className="mb-4 text-sm text-destructive">{error}</p>
            )}
            <div className="flex justify-end">
              <button
                className="rounded-md bg-secondary px-4 py-2 text-sm text-secondary-foreground hover:bg-secondary/80"
                onClick={() => setReuploadTarget(null)}
                disabled={uploading}
              >
                取消
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 删除确认对话框 */}
      {deleteTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-sm rounded-xl bg-card p-6 shadow-xl">
            <h3 className="mb-2 text-lg font-semibold">删除技能</h3>
            <p className="mb-4 text-sm text-muted-foreground">
              确定要删除 &quot;{deleteTarget.name}&quot; 吗？此操作无法撤销，关联文件也将被删除。
            </p>
            <div className="flex justify-end gap-2">
              <button
                className="rounded-md bg-secondary px-4 py-2 text-sm text-secondary-foreground hover:bg-secondary/80"
                onClick={() => setDeleteTarget(null)}
              >
                取消
              </button>
              <button
                className="rounded-md bg-destructive px-4 py-2 text-sm text-destructive-foreground hover:bg-destructive/90"
                onClick={handleDelete}
              >
                删除
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
