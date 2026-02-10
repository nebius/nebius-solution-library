/**
 * SidebarCommon Component
 *
 * Shared sidebar sections rendered at the top of all three mode sidebars:
 * - Mode selector (Step-by-Step / Fine-Tuning / Playground)
 * - NIM Gateway (URL input + health status + reconnect)
 * - Infrastructure (Cluster Scaling)
 *
 * Reads directly from useGateway() and useWorkflow() contexts — no props needed.
 */

import { useState } from 'react';
import { useGateway } from '../contexts/GatewayContext';
import { useWorkflow } from '../contexts/WorkflowContext';
import { ServiceOverviewModal } from './ServiceOverviewModal';
import { K8sScalingPanel } from './K8sScalingPanel';

export function SidebarCommon() {
  const {
    gatewayUrl,
    setGatewayUrl,
    endpoints,
    isCheckingHealth,
    runHealthCheck,
  } = useGateway();

  const { workflowMode, setWorkflowMode } = useWorkflow();

  const [showServiceModal, setShowServiceModal] = useState(false);
  const [showK8sPanel, setShowK8sPanel] = useState(false);

  const readyCount = endpoints.filter((e) => e.status === 'ready').length;
  const requiredEndpoints = endpoints.filter((e) => e.required);
  const requiredReady = requiredEndpoints.filter((e) => e.status === 'ready').length;
  const allRequiredReady = requiredReady === requiredEndpoints.length;
  const hasUrl = gatewayUrl.trim().length > 0;

  return (
    <>
      {/* Workflow Mode Selector */}
      <div className="sidebar-section">
        <h3 className="sidebar-section-title">Workflow Mode</h3>
        <div className="mode-selector">
          <button
            className={`mode-selector-btn ${workflowMode === 'steps' ? 'active' : ''}`}
            onClick={() => setWorkflowMode('steps')}
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M2 3h10M2 7h10M2 11h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
            Step-by-Step
          </button>
          <button
            className={`mode-selector-btn serverless ${workflowMode === 'finetuning' ? 'active' : ''}`}
            onClick={() => setWorkflowMode('finetuning')}
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M7 1L1 4l6 3 6-3-6-3zM1 10l6 3 6-3M1 7l6 3 6-3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            Fine-Tuning
          </button>
          <button
            className={`mode-selector-btn playground ${workflowMode === 'playground' ? 'active' : ''}`}
            onClick={() => setWorkflowMode('playground')}
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <path d="M8 1L2 8h5l-1 5 6-7H7l1-5z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            NIMs
          </button>
        </div>
      </div>

      {/* NIM Gateway */}
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
              onChange={(e) => setGatewayUrl(e.target.value)}
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
                    onClick={runHealthCheck}
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

      {/* Infrastructure / Cluster Scaling */}
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
    </>
  );
}
