/**
 * 表现层 - 工具选择编辑器（用于编辑模式）
 */
import React, { useEffect, useState } from 'react';
import { agentApi } from '@infrastructure/api/agentApi';
import type { ToolDef } from '@infrastructure/api/agentApi';

interface ToolsEditorProps {
  value: string;
  onChange: (value: string) => void;
  label: string;
  description?: string;
}

const CATEGORY_LABELS: Record<string, string> = {
  web_search: '网络搜索',
  web_fetch: '网页获取',
  file: '文件操作',
  clarify: '澄清提问',
  plan: '任务规划',
  general: '通用工具',
};

export const ToolsEditor: React.FC<ToolsEditorProps> = ({
  value,
  onChange,
  label,
  description,
}) => {
  const [tools, setTools] = useState<ToolDef[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterCategory, setFilterCategory] = useState<string>('all');

  // 从 tools_md 内容中解析已选工具
  const parseSelectedTools = (content: string): string[] => {
    const lines = content.split('\n');
    const selected: string[] = [];
    let inEnabledSection = false;

    for (const line of lines) {
      if (line.includes('## 已启用工具')) {
        inEnabledSection = true;
        continue;
      }
      if (inEnabledSection && line.startsWith('- ')) {
        const toolName = line.substring(2).trim();
        if (toolName) {
          selected.push(toolName);
        }
      }
      if (inEnabledSection && line.startsWith('##') && !line.includes('已启用工具')) {
        inEnabledSection = false;
      }
    }

    return selected;
  };

  const selectedTools = parseSelectedTools(value);

  // 生成 tools_md 内容
  const generateToolsMd = (selected: string[]): string => {
    if (selected.length === 0) return '';
    return `# 工具配置\n\n## 已启用工具\n\n${selected.map((t) => `- ${t}`).join('\n')}`;
  };

  useEffect(() => {
    const fetchTools = async () => {
      try {
        setIsLoading(true);
        const response = await agentApi.listTools();
        setTools(response.tools);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : '获取工具列表失败');
      } finally {
        setIsLoading(false);
      }
    };

    fetchTools();
  }, []);

  const handleToggleTool = (toolName: string) => {
    const newSelected = selectedTools.includes(toolName)
      ? selectedTools.filter((t) => t !== toolName)
      : [...selectedTools, toolName];
    onChange(generateToolsMd(newSelected));
  };

  const handleSelectAll = () => {
    const filtered = filteredTools.map((t) => t.name);
    const newSelected = [...new Set([...selectedTools, ...filtered])];
    onChange(generateToolsMd(newSelected));
  };

  const handleDeselectAll = () => {
    const filteredNames = new Set(filteredTools.map((t) => t.name));
    const newSelected = selectedTools.filter((t) => !filteredNames.has(t));
    onChange(generateToolsMd(newSelected));
  };

  const categories = ['all', ...new Set(tools.map((t) => t.category))];
  const filteredTools =
    filterCategory === 'all'
      ? tools
      : tools.filter((t) => t.category === filterCategory);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-center">
          <div className="mx-auto h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent"></div>
          <p className="mt-3 text-sm text-muted-foreground">加载工具列表...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4">
        <p className="text-sm text-destructive">{error}</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-baseline justify-between">
        <label className="text-sm font-medium">{label}</label>
        <span className="text-xs text-muted-foreground">
          {value.length} / 50000
        </span>
      </div>
      {description && (
        <p className="text-xs text-muted-foreground">{description}</p>
      )}

      {/* 分类筛选 */}
      <div className="flex items-center gap-2 border-b pb-3">
        <span className="text-sm font-medium">分类:</span>
        {categories.map((cat) => (
          <button
            key={cat}
            type="button"
            className={`rounded-full px-3 py-1 text-xs transition-colors ${
              filterCategory === cat
                ? 'bg-primary text-primary-foreground'
                : 'bg-secondary text-secondary-foreground hover:bg-secondary/80'
            }`}
            onClick={() => setFilterCategory(cat)}
          >
            {cat === 'all' ? '全部' : CATEGORY_LABELS[cat] || cat}
          </button>
        ))}
      </div>

      {/* 批量操作 */}
      <div className="flex items-center gap-2">
        <button
          type="button"
          className="btn btn-outline px-3 py-1 text-xs"
          onClick={handleSelectAll}
        >
          全选
        </button>
        <button
          type="button"
          className="btn btn-outline px-3 py-1 text-xs"
          onClick={handleDeselectAll}
        >
          取消全选
        </button>
        <span className="ml-auto text-sm text-muted-foreground">
          已选择 {selectedTools.length} 个工具
        </span>
      </div>

      {/* 工具列表 */}
      <div className="space-y-3">
        {filteredTools.length === 0 ? (
          <div className="py-8 text-center text-sm text-muted-foreground">
            该分类下没有可用工具
          </div>
        ) : (
          filteredTools.map((tool) => (
            <ToolCard
              key={tool.name}
              tool={tool}
              isSelected={selectedTools.includes(tool.name)}
              onToggle={() => handleToggleTool(tool.name)}
            />
          ))
        )}
      </div>
    </div>
  );
};

interface ToolCardProps {
  tool: ToolDef;
  isSelected: boolean;
  onToggle: () => void;
}

const ToolCard: React.FC<ToolCardProps> = ({ tool, isSelected, onToggle }) => {
  return (
    <div
      className={`rounded-lg border p-4 transition-all cursor-pointer ${
        isSelected
          ? 'border-primary bg-primary/5'
          : 'border-border hover:border-primary/50'
      }`}
      onClick={onToggle}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <h4 className="font-medium">{tool.name}</h4>
            <span className="rounded-full bg-secondary px-2 py-0.5 text-xs text-secondary-foreground">
              {CATEGORY_LABELS[tool.category] || tool.category}
            </span>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">{tool.description}</p>

          {/* 参数信息 */}
          {tool.parameters.length > 0 && (
            <div className="mt-3">
              <p className="mb-1 text-xs font-medium text-muted-foreground">
                参数:
              </p>
              <div className="flex flex-wrap gap-1">
                {tool.parameters.map((param) => (
                  <span
                    key={param.name}
                    className="rounded bg-secondary/50 px-2 py-0.5 text-xs"
                  >
                    {param.name}
                    {param.required && (
                      <span className="text-destructive">*</span>
                    )}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* 选择框 */}
        <div className="flex-shrink-0">
          <div
            className={`flex h-6 w-6 items-center justify-center rounded border-2 transition-colors ${
              isSelected
                ? 'border-primary bg-primary text-primary-foreground'
                : 'border-border'
            }`}
          >
            {isSelected && (
              <svg
                className="h-4 w-4"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M5 13l4 4L19 7"
                />
              </svg>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
