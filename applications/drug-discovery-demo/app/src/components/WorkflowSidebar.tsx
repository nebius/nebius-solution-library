import { useState } from 'react';
import type { WorkflowStep, WorkflowStepId } from '../types/workflow';
import type { NimEndpoint } from '../data/endpoints';
import { ServiceOverviewModal } from './ServiceOverviewModal';

interface WorkflowSidebarProps {
  steps: WorkflowStep[];
  onStepClick: (stepId: WorkflowStepId) => void;
  gatewayUrl: string;
  onGatewayUrlChange: (url: string) => void;
  endpoints: NimEndpoint[];
  isCheckingHealth: boolean;
  onReconnect: () => void;
}

export function WorkflowSidebar({
  steps,
  onStepClick,
  gatewayUrl,
  onGatewayUrlChange,
  endpoints,
  isCheckingHealth,
  onReconnect,
}: WorkflowSidebarProps) {
  const [showServiceModal, setShowServiceModal] = useState(false);

  const readyCount = endpoints.filter((e) => e.status === 'ready').length;
  const requiredEndpoints = endpoints.filter((e) => e.required);
  const requiredReady = requiredEndpoints.filter((e) => e.status === 'ready').length;
  const allRequiredReady = requiredReady === requiredEndpoints.length;
  const hasUrl = gatewayUrl.trim().length > 0;

  return (
    <aside className="sidebar">
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

          {/* Health Status */}
          {hasUrl && (
            <div className="gateway-status">
              {isCheckingHealth ? (
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

      {/* Workflow Steps */}
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

      {/* Service Overview Modal */}
      {showServiceModal && (
        <ServiceOverviewModal
          endpoints={endpoints}
          gatewayUrl={gatewayUrl}
          onClose={() => setShowServiceModal(false)}
        />
      )}
    </aside>
  );
}
