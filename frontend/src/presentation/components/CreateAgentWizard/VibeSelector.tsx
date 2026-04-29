/**
 * 表现层 - Vibe 选择器组件
 */
import React from 'react';
import { VIBE_OPTIONS, VIBE_LABELS } from '@application/services/useAgentGenerator';

interface VibeSelectorProps {
  selected: string[];
  onChange: (vibes: string[]) => void;
  maxCount?: number;
}

export const VibeSelector: React.FC<VibeSelectorProps> = ({
  selected,
  onChange,
  maxCount = 3,
}) => {
  const toggleVibe = (vibe: string) => {
    if (selected.includes(vibe)) {
      onChange(selected.filter((v) => v !== vibe));
    } else if (selected.length < maxCount) {
      onChange([...selected, vibe]);
    }
  };

  return (
    <div>
      <label className="mb-2 block text-sm font-medium">
        Vibe (1-{maxCount})
      </label>
      <div className="grid grid-cols-2 gap-2">
        {VIBE_OPTIONS.map((vibe) => {
          const isSelected = selected.includes(vibe);
          const isDisabled = !isSelected && selected.length >= maxCount;
          return (
            <button
              key={vibe}
              type="button"
              onClick={() => toggleVibe(vibe)}
              disabled={isDisabled}
              className={`rounded-lg border px-3 py-2 text-left text-sm transition-colors ${
                isSelected
                  ? 'border-primary bg-primary/10 text-primary'
                  : isDisabled
                    ? 'cursor-not-allowed border-border bg-muted text-muted-foreground opacity-50'
                    : 'border-border hover:border-primary/50 hover:bg-accent'
              }`}
            >
              <span className="mr-1.5">{isSelected ? '●' : '○'}</span>
              {VIBE_LABELS[vibe] ?? vibe}
            </button>
          );
        })}
      </div>
      {selected.length === 0 && (
        <p className="mt-1 text-xs text-muted-foreground">请至少选择 1 个</p>
      )}
    </div>
  );
};
