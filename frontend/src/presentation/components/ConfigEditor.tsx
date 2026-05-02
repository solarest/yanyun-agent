/**
 * 表现层 - Markdown 配置编辑器
 */
import React from 'react';

interface ConfigEditorProps {
  value: string;
  onChange: (value: string) => void;
  label: string;
  description?: string;
  maxLength?: number;
  placeholder?: string;
}

export const ConfigEditor: React.FC<ConfigEditorProps> = ({
  value,
  onChange,
  label,
  description,
  maxLength = 50000,
  placeholder,
}) => {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between">
        <label className="text-sm font-medium">{label}</label>
        <span className="text-xs text-muted-foreground">
          {value.length} / {maxLength}
        </span>
      </div>
      {description && (
        <p className="text-xs text-muted-foreground">{description}</p>
      )}
      <textarea
        className="textarea min-h-[400px] w-full font-mono text-sm"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        maxLength={maxLength}
        placeholder={placeholder ?? `输入 ${label} 内容...`}
        spellCheck={false}
      />
    </div>
  );
};
