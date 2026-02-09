import { useState } from 'react';
import type { WorkflowStep, WorkflowStepId } from '../types/workflow';
import type { NimEndpoint } from '../data/endpoints';
import type { DrugTarget } from '../data/drugs';
import { ServiceOverviewModal } from './ServiceOverviewModal';
import { K8sScalingPanel } from './K8sScalingPanel';

type WorkflowMode = 'steps' | 'agent' | 'finetuning';

interface WorkflowSidebarProps {
  steps: WorkflowStep[];
  onStepClick: (stepId: WorkflowStepId) => void;
  gatewayUrl: string;
  onGatewayUrlChange: (url: string) => void;
  endpoints: NimEndpoint[];
  isCheckingHealth: boolean;
  onReconnect: () => void;
  workflowMode?: WorkflowMode;
  onWorkflowModeChange?: (mode: WorkflowMode) => void;
  hideWorkflowSteps?: boolean;
  // Drug target selection (for agent mode)
  drugTargets?: DrugTarget[];
  selectedDrugId?: string | null;
  onSelectDrug?: (drugId: string | null) => void;
  // Demo mode
  demoMode?: boolean;
  onDemoModeChange?: (enabled: boolean) => void;
}

export function WorkflowSidebar({
  steps,
  onStepClick,
  gatewayUrl,
  onGatewayUrlChange,
  endpoints,
  isCheckingHealth,
  onReconnect,
  workflowMode = 'steps',
  onWorkflowModeChange,
  hideWorkflowSteps = false,
  drugTargets,
  selectedDrugId,
  onSelectDrug,
  demoMode = false,
  onDemoModeChange: _onDemoModeChange,
}: WorkflowSidebarProps) {
  const [showServiceModal, setShowServiceModal] = useState(false);
  const [showK8sPanel, setShowK8sPanel] = useState(false);

  const readyCount = endpoints.filter((e) => e.status === 'ready').length;
  const requiredEndpoints = endpoints.filter((e) => e.required);
  const requiredReady = requiredEndpoints.filter((e) => e.status === 'ready').length;
  const allRequiredReady = requiredReady === requiredEndpoints.length;
  const hasUrl = gatewayUrl.trim().length > 0 || demoMode;

  return (
    <aside className="sidebar">
      {/* Workflow Mode Selector */}
      {onWorkflowModeChange && (
        <div className="sidebar-section">
          <h3 className="sidebar-section-title">Workflow Mode</h3>
          <div className="mode-selector">
            <button
              className={`mode-selector-btn ${workflowMode === 'agent' ? 'active' : ''}`}
              onClick={() => onWorkflowModeChange('agent')}
            >
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M7 1l6 4v4l-6 4-6-4V5l6-4z" stroke="currentColor" strokeWidth="1.5" />
                <circle cx="7" cy="7" r="2" fill="currentColor" />
              </svg>
              AI Agent
            </button>
            <button
              className={`mode-selector-btn ${workflowMode === 'steps' ? 'active' : ''}`}
              onClick={() => onWorkflowModeChange('steps')}
            >
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M2 3h10M2 7h10M2 11h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
              Step-by-Step
            </button>
            <button
              className={`mode-selector-btn serverless ${workflowMode === 'finetuning' ? 'active' : ''}`}
              onClick={() => onWorkflowModeChange('finetuning')}
            >
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M7 1L1 4l6 3 6-3-6-3zM1 10l6 3 6-3M1 7l6 3 6-3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              Fine-Tuning
            </button>
          </div>
        </div>
      )}

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
              xmlns="http://www.w3.org/2000/svg"
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
            <span className="settings-panel-title">NIM Gateway</span>
          </div>

          {/* Demo Mode Toggle - Hidden for now */}
          {/* {_onDemoModeChange && (
            <div className="demo-mode-toggle">
              <label className="toggle-label">
                <input
                  type="checkbox"
                  checked={demoMode}
                  onChange={(e) => _onDemoModeChange(e.target.checked)}
                  className="toggle-input"
                />
                <span className="toggle-switch" />
                <span className="toggle-text">Demo Mode</span>
              </label>
              {demoMode && (
                <span className="demo-mode-badge">Using mock data</span>
              )}
            </div>
          )} */}

          {!demoMode && (
            <div className="form-group">
              <label className="form-label" htmlFor="gateway-url">
                Inference Cluster URL
              </label>
              <input
                id="gateway-url"
                type="text"
                className="form-input"
                placeholder="http://10.0.0.1"
                value={gatewayUrl}
                onChange={(e) => onGatewayUrlChange(e.target.value)}
              />
            </div>
          )}

          {/* Health Status */}
          {hasUrl && (
            <div className="gateway-status">
              {demoMode ? (
                <div className="gateway-status-result ready">
                  <span className="status-dot connected" />
                  <span>Demo mode active - all services simulated</span>
                </div>
              ) : isCheckingHealth ? (
                <div className="gateway-status-checking">
                  <span className="spinner spinner-sm" />
                  <span>Checking services...</span>
                </div>
              ) : (
                <>
                  <div
                    className={`gateway-status-result gateway-status-clickable ${allRequiredReady ? 'ready' : 'not-ready'}`}
                    onClick={() => setShowServiceModal(true)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => e.key === 'Enter' && setShowServiceModal(true)}
                  >
                    <span className={`status-dot ${allRequiredReady ? 'connected' : 'disconnected'}`} />
                    <span>
                      {readyCount}/{endpoints.length} services ready
                    </span>
                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" style={{ marginLeft: 'auto' }}>
                      <path d="M4.5 9l3-3-3-3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </div>
                  <button
                    className="btn btn-ghost btn-sm reconnect-btn"
                    onClick={onReconnect}
                  >
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                      <path
                        d="M1 7a6 6 0 0 1 10.196-4.318M13 7a6 6 0 0 1-10.196 4.318"
                        stroke="currentColor"
                        strokeWidth="1.5"
                        strokeLinecap="round"
                      />
                      <path
                        d="M11 1v3h-3M3 13v-3h3"
                        stroke="currentColor"
                        strokeWidth="1.5"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                    Reconnect
                  </button>
                </>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Drug Target Selector (for agent mode) */}
      {drugTargets && onSelectDrug && (
        <div className="sidebar-section">
          <h3 className="sidebar-section-title">Drug Target</h3>
          <select
            className="form-select"
            value={selectedDrugId || ''}
            onChange={(e) => onSelectDrug(e.target.value || null)}
          >
            <option value="">Select a drug target...</option>
            {drugTargets.filter(d => !d.isCustom).map((drug) => (
              <option key={drug.id} value={drug.id}>
                {drug.name}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Cluster Scaling */}
      <div className="sidebar-section">
        <h3 className="sidebar-section-title">Infrastructure</h3>
        <button
          className="sidebar-k8s-btn"
          onClick={() => setShowK8sPanel(true)}
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path
              d="M8 1.5L2 5v6l6 3.5 6-3.5V5L8 1.5z"
              stroke="currentColor"
              strokeWidth="1.25"
              strokeLinejoin="round"
            />
            <circle cx="8" cy="8" r="1.5" fill="currentColor" />
          </svg>
          <span>Cluster Scaling</span>
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none" style={{ marginLeft: 'auto' }}>
            <path d="M4.5 9l3-3-3-3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>

      {/* Workflow Steps */}
      {!hideWorkflowSteps && (
        <div className="sidebar-section">
          <h3 className="sidebar-section-title">Workflow</h3>
          <div className="workflow-steps">
            {steps.map((step, index) => (
              <button
                key={step.id}
                className={`workflow-step ${step.status}`}
                onClick={() => onStepClick(step.id)}
              >
                <span className="workflow-step-number">
                  {step.status === 'completed' ? (
                    <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                      <path
                        d="M11.5 4L5.5 10L2.5 7"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  ) : (
                    index + 1
                  )}
                </span>
                <div className="workflow-step-content">
                  <div className="workflow-step-title">{step.title}</div>
                  <div className="workflow-step-subtitle">{step.subtitle}</div>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Service Overview Modal */}
      {showServiceModal && (
        <ServiceOverviewModal
          endpoints={endpoints}
          gatewayUrl={gatewayUrl}
          onClose={() => setShowServiceModal(false)}
        />
      )}

      {/* K8s Scaling Panel */}
      <K8sScalingPanel
        isOpen={showK8sPanel}
        onClose={() => setShowK8sPanel(false)}
      />
    </aside>
  );
}
