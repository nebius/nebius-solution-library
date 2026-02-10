/**
 * FineTuningSidebar Component
 *
 * Sidebar navigation for the Fine-Tuning workflow.
 * Shows shared sections (mode selector, gateway, infra) via SidebarCommon,
 * plus fine-tuning-specific steps and model info.
 */

import { useFineTuning } from '../../contexts/FineTuningContext';
import { SidebarCommon } from '../SidebarCommon';
import type { FineTuningStep, FineTuningStepId } from '../../types/finetuning';

interface FineTuningSidebarProps {
  steps: FineTuningStep[];
}

export function FineTuningSidebar({
  steps,
}: FineTuningSidebarProps) {
  const { goToStep, canNavigateToStep, trainingStatus, selectedModel } = useFineTuning();

  const handleStepClick = (stepId: FineTuningStepId) => {
    if (canNavigateToStep(stepId)) {
      goToStep(stepId);
    }
  };

  return (
    <aside className="sidebar">
      <SidebarCommon />

      {/* Nebius Jobs Branding */}
      <div className="sidebar-section">
        <div className="serverless-brand">
          <div className="serverless-brand-icon">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
              <path
                d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
          <div className="serverless-brand-text">
            <span className="serverless-brand-title">Nebius Jobs</span>
            <span className="serverless-brand-subtitle">GPU Fine-Tuning</span>
          </div>
        </div>
      </div>

      {/* Selected Model Info */}
      {selectedModel && (
        <div className="sidebar-section">
          <div className="gpu-info-panel">
            <div className="gpu-info-header">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M8 2a6 6 0 100 12A6 6 0 008 2zm0 2v4l3 1.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
              <span>Selected Model</span>
            </div>
            <div className="gpu-info-details">
              <div className="gpu-info-item">
                <span className="gpu-info-label">Model</span>
                <span className="gpu-info-value">{selectedModel.name}</span>
              </div>
              <div className="gpu-info-item">
                <span className="gpu-info-label">Type</span>
                <span className="gpu-info-value" style={{ textTransform: 'capitalize' }}>{selectedModel.modality}</span>
              </div>
              <div className="gpu-info-item">
                <span className="gpu-info-label">Task</span>
                <span className="gpu-info-value" style={{ textTransform: 'capitalize' }}>{selectedModel.taskType}</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Workflow Steps */}
      <div className="sidebar-section">
        <h3 className="sidebar-section-title">Workflow</h3>
        <div className="workflow-steps">
          {steps.map((step, index) => (
            <button
              key={step.id}
              className={`workflow-step ${step.status}`}
              onClick={() => handleStepClick(step.id)}
              disabled={!canNavigateToStep(step.id)}
            >
              <div className="workflow-step-indicator">
                {step.status === 'completed' ? (
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                    <path
                      d="M2.5 6l2.5 2.5 5-5"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                ) : (
                  <span>{index + 1}</span>
                )}
              </div>
              <div className="workflow-step-content">
                <span className="workflow-step-title">{step.title}</span>
                <span className="workflow-step-subtitle">{step.subtitle}</span>
              </div>
              {step.id === 'training' && trainingStatus?.state === 'running' && (
                <span className="workflow-step-badge pulse">Training</span>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* GPU Info */}
      <div className="sidebar-section">
        <div className="gpu-info-panel">
          <div className="gpu-info-header">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <rect x="2" y="4" width="12" height="8" rx="1" stroke="currentColor" strokeWidth="1.5" />
              <path d="M5 7h6M5 9h4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
            <span>GPU Resources</span>
          </div>
          <div className="gpu-info-details">
            <div className="gpu-info-item">
              <span className="gpu-info-label">Platform</span>
              <span className="gpu-info-value">H200 SXM</span>
            </div>
            <div className="gpu-info-item">
              <span className="gpu-info-label">Memory</span>
              <span className="gpu-info-value">80 GB</span>
            </div>
            <div className="gpu-info-item">
              <span className="gpu-info-label">Rate</span>
              <span className="gpu-info-value">$6.00/hr</span>
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
}
