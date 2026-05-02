/**
 * 表现层 - Identity & Model 步骤
 */
import React from 'react';
import { VibeSelector } from '../VibeSelector';
import { AVATAR_COLOR_OPTIONS, LivePreview } from '../LivePreview';
import type { GeneratedContent } from '@application/services/useAgentGenerator';

interface IdentityModelStepProps {
  name: string;
  description: string;
  vibes: string[];
  avatarColor: string;
  generated: GeneratedContent | null;
  onNameChange: (name: string) => void;
  onDescriptionChange: (desc: string) => void;
  onVibesChange: (vibes: string[]) => void;
  onAvatarColorChange: (color: string) => void;
}

export const IdentityModelStep: React.FC<IdentityModelStepProps> = ({
  name,
  description,
  vibes,
  avatarColor,
  generated,
  onNameChange,
  onDescriptionChange,
  onVibesChange,
  onAvatarColorChange,
}) => {
  return (
    <div className="flex gap-6">
      {/* 左侧表单 (60%) */}
      <div className="flex-[3] space-y-5">
        {/* Name */}
        <div>
          <label className="mb-1 block text-sm font-medium">Name</label>
          <input
            type="text"
            className="input w-full"
            value={name}
            onChange={(e) => onNameChange(e.target.value)}
            placeholder="例如：小助手"
            maxLength={100}
          />
        </div>

        {/* Description */}
        <div>
          <label className="mb-1 block text-sm font-medium">Description</label>
          <textarea
            className="textarea min-h-[80px] w-full"
            value={description}
            onChange={(e) => onDescriptionChange(e.target.value)}
            placeholder="帮助你管理日程和提醒的智能助手"
            maxLength={500}
          />
        </div>

        {/* Vibes */}
        <VibeSelector selected={vibes} onChange={onVibesChange} />

        <div>
          <label className="mb-2 block text-sm font-medium">Avatar Color</label>
          <div className="flex flex-wrap gap-2">
            {AVATAR_COLOR_OPTIONS.map((color) => {
              const selected = color === avatarColor;
              return (
                <button
                  key={color}
                  type="button"
                  aria-label={`Choose avatar color ${color}`}
                  aria-pressed={selected}
                  onClick={() => onAvatarColorChange(color)}
                  className={`h-8 w-8 rounded-full border-2 transition ${
                    selected
                      ? 'border-foreground ring-2 ring-ring ring-offset-2'
                      : 'border-transparent hover:border-border'
                  }`}
                  style={{ backgroundColor: color }}
                />
              );
            })}
          </div>
        </div>
      </div>

      {/* 右侧预览 (40%) */}
      <div className="flex-[2]">
        <div className="sticky top-4">
          <LivePreview
            name={name}
            description={description}
            vibes={vibes}
            generated={generated}
            avatarColor={avatarColor}
          />
        </div>
      </div>
    </div>
  );
};
