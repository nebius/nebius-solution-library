/**
 * FineTuningSidebar Component
 *
 * Sidebar navigation for the Fine-Tuning workflow.
 * Shows workflow steps, connection settings, and Nebius branding.
 */

import { useFineTuning } from '../../contexts/FineTuningContext';
import type { FineTuningStep, FineTuningStepId } from '../../types/finetuning';

interface FineTuningSidebarProps {
  steps: FineTuningStep[];
  gatewayUrl: string;
  onGatewayUrlChange: (url: string) => void;
  onBack: () => void;
}

export function FineTuningSidebar({
  steps,
  gatewayUrl,
  onGatewayUrlChange,
  onBack,
}: FineTuningSidebarProps) {
  const { goToStep, canNavigateToStep, trainingStatus } = useFineTuning();

  const handleStepClick = (stepId: FineTuningStepId) => {
    if (canNavigateToStep(stepId)) {
      goToStep(stepId);
    }
  };

  return (
    <aside className="sidebar">
      {/* Back Button */}
      <div className="sidebar-section">
        <button className="btn btn-ghost btn-sm" onClick={onBack} style={{ width: '100%' }}>
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path
              d="M9 11L5 7l4-4"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          Back to Workflows
        </button>
      </div>

      {/* Nebius Serverless Branding */}
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
            <span className="serverless-brand-title">Nebius Serverless</span>
            <span className="serverless-brand-subtitle">GPU Fine-Tuning</span>
          </div>
        </div>
      </div>

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

      {/* Connection Settings */}
      <div className="sidebar-section">
        <div className="settings-panel">
          <div className="settings-panel-header">
            <svg
              className="settings-panel-icon"
              width="16"
              height="16"
              viewBox="0 0 16 16"
              fill="none"
            >
              <path
                d="M8 10a2 2 0 100-4 2 2 0 000 4z"
                stroke="currentColor"
                strokeWidth="1.5"
              />
              <path
                d="M13.5 8a5.5 5.5 0 11-11 0 5.5 5.5 0 0111 0z"
                stroke="currentColor"
                strokeWidth="1.5"
              />
            </svg>
            <span className="settings-panel-title">Nebius API</span>
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="gateway-url-ft">
              Gateway URL
            </label>
            <input
              id="gateway-url-ft"
              type="text"
              className="form-input"
              placeholder="http://10.0.0.1"
              value={gatewayUrl}
              onChange={(e) => onGatewayUrlChange(e.target.value)}
            />
          </div>

          <div className="connection-status">
            {gatewayUrl ? (
              <span className="connection-status-badge connected">
                <span className="status-dot" />
                Connected
              </span>
            ) : (
              <span className="connection-status-badge demo">
                <span className="status-dot" />
                Demo Mode
              </span>
            )}
          </div>
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
