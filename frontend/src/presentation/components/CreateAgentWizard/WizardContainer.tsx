/**
 * 表现层 - 创建 Agent 向导容器
 */
import React, { useState, useMemo } from 'react';
import { StepIndicator } from './StepIndicator';
import { IdentityModelStep } from './steps/IdentityModelStep';
import { ToolsStep } from './steps/ToolsStep';
import {
  useAgentGenerator,
  type GeneratedContent,
} from '@application/services/useAgentGenerator';
import type { CreateAgentRequest } from '@domain/entities/agent';

const WIZARD_STEPS = [
  { id: 'identity', label: 'Identity & Model' },
  { id: 'tools', label: 'Tools' },
  { id: 'review', label: 'Review & Create' },
];

interface WizardContainerProps {
  onSubmit: (data: CreateAgentRequest) => void;
  onCancel: () => void;
  isLoading: boolean;
}

export const WizardContainer: React.FC<WizardContainerProps> = ({
  onSubmit,
  onCancel,
  isLoading,
}) => {
  const [currentStep, setCurrentStep] = useState(0);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [vibes, setVibes] = useState<string[]>([]);
  const [selectedTools, setSelectedTools] = useState<string[]>([]);

  const { generate } = useAgentGenerator();

  const generated: GeneratedContent | null = useMemo(() => {
    if (!name) return null;
    return generate({
      name,
      description,
      vibes,
    });
  }, [name, description, vibes, generate]);

  const canProceed =
    name.trim().length > 0 && vibes.length > 0 && description.trim().length > 0;

  const handleNext = () => {
    if (currentStep < WIZARD_STEPS.length - 1) {
      setCurrentStep(currentStep + 1);
    }
  };

  const handleBack = () => {
    if (currentStep > 0) {
      setCurrentStep(currentStep - 1);
    } else {
      onCancel();
    }
  };

  const handleSubmit = () => {
    if (!generated) return;
    
    // 生成 tools_md 内容
    const toolsMd = selectedTools.length > 0
      ? `# 工具配置\n\n## 已启用工具\n\n${selectedTools.map((t) => `- ${t}`).join('\n')}`
      : '';
    
    onSubmit({
      name: name.trim(),
      description: description.trim(),
      vibes,
      ...generated,
      tools_md: toolsMd,  // 覆盖 generated 中的 tools_md
    });
  };

  return (
    <div className="flex h-full flex-col">
      {/* 头部：步骤指示器 */}
      <div className="border-b px-6 py-4">
        <h2 className="mb-3 text-xl font-semibold">Create Agent</h2>
        <StepIndicator steps={WIZARD_STEPS} currentStep={currentStep} />
      </div>

      {/* 内容区 */}
      <div className="flex-1 overflow-y-auto p-6">
        {currentStep === 0 && (
          <IdentityModelStep
            name={name}
            description={description}
            vibes={vibes}
            generated={generated}
            onNameChange={setName}
            onDescriptionChange={setDescription}
            onVibesChange={setVibes}
          />
        )}

        {currentStep === 1 && (
          <ToolsStep
            selectedTools={selectedTools}
            onToolsChange={setSelectedTools}
          />
        )}

        {currentStep === 2 && generated && (
          <div className="space-y-4">
            <h3 className="text-lg font-medium">Review Generated Config</h3>
            <p className="text-sm text-muted-foreground">
              以下配置文件已根据你的输入自动生成，创建后可在编辑页面进一步修改。
            </p>
            {Object.entries(generated).map(([key, value]) => {
              if (!value) return null;
              const label = key.replace('_md', '.md').toUpperCase();
              return (
                <div key={key} className="rounded-lg border p-4">
                  <h4 className="mb-2 text-sm font-medium">{label}</h4>
                  <pre className="max-h-40 overflow-y-auto whitespace-pre-wrap text-xs text-muted-foreground">
                    {value}
                  </pre>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* 底部导航 */}
      <div className="flex items-center justify-between border-t px-6 py-4">
        <button
          type="button"
          className="btn btn-outline"
          onClick={handleBack}
          disabled={isLoading}
        >
          {currentStep === 0 ? 'Cancel' : 'Back'}
        </button>
        <div>
          {currentStep === 0 && (
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleNext}
              disabled={!canProceed}
            >
              Next: Tools
            </button>
          )}
          {currentStep === 1 && (
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleNext}
            >
              Next: Review
            </button>
          )}
          {currentStep === 2 && (
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleSubmit}
              disabled={isLoading || !generated}
            >
              {isLoading ? 'Creating...' : 'Create Agent'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
