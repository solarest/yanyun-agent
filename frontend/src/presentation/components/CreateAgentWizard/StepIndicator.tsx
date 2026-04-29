/**
 * 表现层 - 步骤指示器组件
 */
import React from 'react';

interface Step {
  id: string;
  label: string;
}

interface StepIndicatorProps {
  steps: Step[];
  currentStep: number;
}

export const StepIndicator: React.FC<StepIndicatorProps> = ({
  steps,
  currentStep,
}) => {
  return (
    <div className="flex items-center gap-2">
      {steps.map((step, index) => (
        <React.Fragment key={step.id}>
          <div className="flex items-center gap-2">
            <div
              className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-medium ${
                index <= currentStep
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted text-muted-foreground'
              }`}
            >
              {index < currentStep ? '✓' : index + 1}
            </div>
            <span
              className={`text-sm ${
                index <= currentStep
                  ? 'font-medium text-foreground'
                  : 'text-muted-foreground'
              }`}
            >
              {step.label}
            </span>
          </div>
          {index < steps.length - 1 && (
            <div
              className={`h-px flex-1 ${
                index < currentStep ? 'bg-primary' : 'bg-border'
              }`}
            />
          )}
        </React.Fragment>
      ))}
    </div>
  );
};
