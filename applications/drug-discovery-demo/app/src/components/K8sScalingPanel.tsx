/**
 * K8s Scaling Panel
 * Dashboard for viewing cluster capacity and scaling NIM deployments
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { createPortal } from 'react-dom';
import {
  checkK8sHealth,
  getDeployments,
  getClusterCapacity,
  scaleDeployment,
  getNodeGroups,
  scaleNodeGroup,
  type K8sDeployment,
  type ClusterCapacity,
  type NodeGroup,
} from '../services/k8sService';
import { getGpuColor, getGpuDisplayName, type GpuType } from '../data/k8sMapping';

interface K8sScalingPanelProps {
  isOpen: boolean;
  onClose: () => void;
}

export function K8sScalingPanel({ isOpen, onClose }: K8sScalingPanelProps) {
  const [isConnected, setIsConnected] = useState(false);
  const [context, setContext] = useState<string>('');
  const [deployments, setDeployments] = useState<K8sDeployment[]>([]);
  const [capacity, setCapacity] = useState<ClusterCapacity | null>(null);
  const [nodeGroups, setNodeGroups] = useState<NodeGroup[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [scalingDeployment, setScalingDeployment] = useState<string | null>(null);
  const [scalingNodeGroup, setScalingNodeGroup] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [errorDetails, setErrorDetails] = useState<{ traceId?: string; suggestion?: string } | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  // Handle ESC key to close modal
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // Focus trap and initial focus
  useEffect(() => {
    if (isOpen && panelRef.current) {
      panelRef.current.focus();
    }
  }, [isOpen]);

  const refresh = useCallback(async () => {
    try {
      const health = await checkK8sHealth();
      setIsConnected(health.connected);
      setContext(health.context || '');

      if (health.connected) {
        const [deps, cap, groups] = await Promise.all([
          getDeployments(),
          getClusterCapacity(),
          getNodeGroups(),
        ]);
        setDeployments(deps);
        setCapacity(cap);
        setNodeGroups(groups);
        setError(null);
      }
    } catch (err) {
      setError('Failed to fetch cluster data');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      refresh();
      const interval = setInterval(refresh, 5000);
      return () => clearInterval(interval);
    }
  }, [isOpen, refresh]);

  const handleScale = useCallback(async (deployment: K8sDeployment, delta: number) => {
    const newReplicas = Math.max(0, deployment.replicas + delta);

    setScalingDeployment(deployment.name);
    setError(null);

    const result = await scaleDeployment(deployment.name, newReplicas);

    if (result.success) {
      // Optimistically update UI
      setDeployments((prev) =>
        prev.map((d) =>
          d.name === deployment.name ? { ...d, replicas: newReplicas } : d
        )
      );
    } else {
      setError(result.error || 'Failed to scale');
    }

    setScalingDeployment(null);
  }, []);

  const handleScaleNodeGroup = useCallback(async (nodeGroup: NodeGroup, delta: number) => {
    const newCount = Math.max(0, nodeGroup.nodeCount + delta);

    setScalingNodeGroup(nodeGroup.id);
    setError(null);
    setErrorDetails(null);

    const result = await scaleNodeGroup(nodeGroup.id, newCount);

    if (result.success) {
      // Optimistically update UI
      setNodeGroups((prev) =>
        prev.map((ng) =>
          ng.id === nodeGroup.id
            ? { ...ng, nodeCount: newCount, totalGpus: newCount * ng.gpuPerNode }
            : ng
        )
      );
      // Also update capacity using the node group's GPU type
      if (capacity) {
        const gpuDelta = delta * nodeGroup.gpuPerNode;
        const gpuType = nodeGroup.gpuType || Object.keys(capacity.totalGpus)[0] || 'GPU';
        setCapacity({
          ...capacity,
          totalGpus: {
            ...capacity.totalGpus,
            [gpuType]: (capacity.totalGpus[gpuType] || 0) + gpuDelta,
          },
          availableGpus: {
            ...capacity.availableGpus,
            [gpuType]: (capacity.availableGpus[gpuType] || 0) + gpuDelta,
          },
        });
      }
    } else {
      setError(result.error || 'Failed to scale node group');
      if (result.traceId || result.suggestion) {
        setErrorDetails({
          traceId: result.traceId,
          suggestion: result.suggestion,
        });
      }
    }

    setScalingNodeGroup(null);
  }, [capacity]);

  if (!isOpen) return null;

  return createPortal(
    <div
      className="k8s-panel-overlay"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="k8s-panel-title"
    >
      <div
        className="k8s-panel"
        onClick={(e) => e.stopPropagation()}
        ref={panelRef}
        tabIndex={-1}
      >
        <div className="k8s-panel-header">
          <div className="k8s-panel-title">
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
              <path
                d="M10 2L3 6v8l7 4 7-4V6l-7-4z"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinejoin="round"
              />
              <circle cx="10" cy="10" r="2" fill="currentColor" />
            </svg>
            <span id="k8s-panel-title">Cluster Scaling</span>
          </div>
          <button className="k8s-panel-close" onClick={onClose} aria-label="Close panel">
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
              <path d="M5 5l10 10M15 5L5 15" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
          </button>
        </div>

        {isLoading ? (
          <div className="k8s-loading">
            <span className="spinner" />
            <span>Connecting to cluster...</span>
          </div>
        ) : !isConnected ? (
          <div className="k8s-disconnected">
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
              <circle cx="24" cy="24" r="20" stroke="currentColor" strokeWidth="2" strokeDasharray="4 4" />
              <path d="M24 16v8M24 28v2" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
            <h3>kubectl not connected</h3>
            <p>Ensure kubectl is configured and connected to your cluster.</p>
            <code>kubectl config current-context</code>
            <button className="btn btn-primary" onClick={refresh}>
              Retry Connection
            </button>
          </div>
        ) : (
          <>
            {/* Connection Status */}
            <div className="k8s-context">
              <span className="k8s-context-dot" />
              <span>Connected to: {context}</span>
              <button className="btn btn-ghost btn-sm" onClick={refresh} aria-label="Refresh cluster data">
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <path
                    d="M1 7a6 6 0 1 0 1.5-4M1 1v3h3"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </button>
            </div>

            {/* Error Message */}
            {error && (
              <div className="k8s-error" role="alert">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.5" />
                  <path d="M8 5v4M8 11v.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
                <div className="k8s-error-content">
                  <span>{error}</span>
                  {errorDetails?.suggestion && (
                    <p className="k8s-error-suggestion">{errorDetails.suggestion}</p>
                  )}
                  {errorDetails?.traceId && (
                    <code className="k8s-error-trace">Trace ID: {errorDetails.traceId}</code>
                  )}
                </div>
                <button onClick={() => { setError(null); setErrorDetails(null); }}>Dismiss</button>
              </div>
            )}

            {/* Cluster Capacity */}
            {capacity && (
              <div className="k8s-capacity">
                <h3>GPU Capacity</h3>
                <div className="k8s-gpu-bars">
                  {(Object.keys(capacity.totalGpus) as GpuType[]).map((gpuType) => {
                    const total = capacity.totalGpus[gpuType];
                    const used = capacity.usedGpus[gpuType];
                    if (total === 0) return null;

                    const percentage = (used / total) * 100;
                    return (
                      <div key={gpuType} className="k8s-gpu-bar">
                        <div className="k8s-gpu-bar-header">
                          <span
                            className="k8s-gpu-type"
                            style={{ color: getGpuColor(gpuType) }}
                          >
                            {getGpuDisplayName(gpuType)}
                          </span>
                          <span className="k8s-gpu-count">
                            {used}/{total}
                          </span>
                        </div>
                        <div className="k8s-gpu-bar-track">
                          <div
                            className="k8s-gpu-bar-fill"
                            style={{
                              width: `${percentage}%`,
                              backgroundColor: getGpuColor(gpuType),
                            }}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Node Groups / GPU Instances */}
            {nodeGroups.length > 0 && (
              <div className="k8s-nodegroups">
                <h3>GPU Node Groups</h3>
                <p className="k8s-nodegroups-description">
                  Scale the underlying GPU instances to add more capacity
                </p>
                <div className="k8s-nodegroup-list">
                  {nodeGroups.map((ng) => (
                    <div key={ng.id} className="k8s-nodegroup-card">
                      <div className="k8s-nodegroup-info">
                        <span className="k8s-nodegroup-name">{ng.name}</span>
                        <span className="k8s-nodegroup-details">
                          {ng.gpuPerNode}x {ng.gpuType} per node · {ng.totalGpus} GPUs total
                        </span>
                      </div>
                      <div className="k8s-nodegroup-controls">
                        <button
                          className="k8s-scale-btn"
                          onClick={() => handleScaleNodeGroup(ng, -1)}
                          disabled={ng.nodeCount <= 0 || scalingNodeGroup === ng.id}
                          aria-label={`Remove one ${ng.name} instance`}
                        >
                          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                            <path d="M4 8h8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                          </svg>
                        </button>
                        <span className="k8s-nodegroup-count">
                          {scalingNodeGroup === ng.id ? (
                            <span className="spinner spinner-sm" />
                          ) : (
                            <>
                              {ng.nodeCount} <span className="k8s-nodegroup-count-label">nodes</span>
                            </>
                          )}
                        </span>
                        <button
                          className="k8s-scale-btn k8s-scale-btn-up"
                          onClick={() => handleScaleNodeGroup(ng, 1)}
                          disabled={scalingNodeGroup === ng.id}
                          aria-label={`Add one ${ng.name} instance`}
                        >
                          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                            <path d="M8 4v8M4 8h8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                          </svg>
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Deployments */}
            <div className="k8s-deployments">
              <h3>NIM Deployments</h3>
              <div className="k8s-deployment-list">
                {deployments.map((dep) => (
                  <div
                    key={dep.name}
                    className={`k8s-deployment-card ${dep.status}`}
                  >
                    <div className="k8s-deployment-header">
                      <span className="k8s-deployment-name">{dep.displayName}</span>
                      <span
                        className="k8s-deployment-gpu"
                        style={{ backgroundColor: getGpuColor(dep.gpuType) }}
                      >
                        {dep.gpuCount}x {dep.gpuType}
                      </span>
                    </div>

                    <div className="k8s-deployment-replicas">
                      <div className="k8s-replica-dots">
                        {Array.from({ length: Math.max(dep.replicas, 5) }).map((_, i) => (
                          <span
                            key={i}
                            className={`k8s-replica-dot ${
                              i < dep.readyReplicas
                                ? 'ready'
                                : i < dep.availableReplicas
                                ? 'available'
                                : i < dep.replicas
                                ? 'pending'
                                : ''
                            }`}
                          />
                        ))}
                      </div>
                      <span className="k8s-replica-count">
                        {dep.availableReplicas}/{dep.replicas} pods
                      </span>
                    </div>

                    <div className="k8s-deployment-actions">
                      <button
                        className="k8s-scale-btn"
                        onClick={() => handleScale(dep, -1)}
                        disabled={dep.replicas <= 0 || scalingDeployment === dep.name}
                        aria-label={`Scale down ${dep.displayName}`}
                      >
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                          <path d="M4 8h8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                        </svg>
                      </button>
                      <span className="k8s-scale-value" aria-live="polite">
                        {scalingDeployment === dep.name ? (
                          <span className="spinner spinner-sm" aria-label="Scaling in progress" />
                        ) : (
                          dep.replicas
                        )}
                      </span>
                      <button
                        className="k8s-scale-btn"
                        onClick={() => handleScale(dep, 1)}
                        disabled={scalingDeployment === dep.name}
                        aria-label={`Scale up ${dep.displayName}`}
                      >
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                          <path d="M8 4v8M4 8h8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                        </svg>
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Quick Actions */}
            <div className="k8s-quick-actions-section">
              <h3>Quick Actions</h3>
              <div className="k8s-quick-actions-grid">
                {/* Scale Up Actions */}
                <button
                  className="btn btn-primary"
                  onClick={async () => {
                    for (const dep of deployments) {
                      if (dep.replicas === 0) {
                        await scaleDeployment(dep.name, 1);
                      }
                    }
                    refresh();
                  }}
                  disabled={deployments.every(d => d.replicas > 0)}
                >
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <path d="M4 4l12 6-12 6V4z" fill="currentColor" />
                  </svg>
                  Start All NIMs
                </button>
                <button
                  className="btn btn-outline"
                  onClick={async () => {
                    for (const dep of deployments) {
                      await scaleDeployment(dep.name, dep.replicas + 1);
                    }
                    refresh();
                  }}
                >
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <path d="M8 4v8M4 8h8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                  </svg>
                  Scale All +1
                </button>
                <button
                  className="btn btn-outline"
                  onClick={async () => {
                    for (const dep of deployments) {
                      if (['openfold3', 'boltz2', 'openfold2'].includes(dep.nimId)) {
                        await scaleDeployment(dep.name, 2);
                      }
                    }
                    refresh();
                  }}
                >
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <circle cx="5" cy="8" r="3" stroke="currentColor" strokeWidth="1.5" />
                    <circle cx="11" cy="8" r="3" stroke="currentColor" strokeWidth="1.5" />
                  </svg>
                  Structure NIMs → 2
                </button>
                <button
                  className="btn btn-outline"
                  onClick={async () => {
                    for (const dep of deployments) {
                      if (['openfold3', 'boltz2', 'diffdock'].includes(dep.nimId)) {
                        await scaleDeployment(dep.name, 3);
                      }
                    }
                    refresh();
                  }}
                >
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <circle cx="4" cy="8" r="2.5" stroke="currentColor" strokeWidth="1.5" />
                    <circle cx="8" cy="8" r="2.5" stroke="currentColor" strokeWidth="1.5" />
                    <circle cx="12" cy="8" r="2.5" stroke="currentColor" strokeWidth="1.5" />
                  </svg>
                  Parallel NIMs → 3
                </button>

                {/* Scale Down Actions */}
                <button
                  className="btn btn-ghost"
                  onClick={async () => {
                    for (const dep of deployments) {
                      if (dep.replicas > 1) {
                        await scaleDeployment(dep.name, dep.replicas - 1);
                      }
                    }
                    refresh();
                  }}
                  disabled={deployments.every(d => d.replicas <= 1)}
                >
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <path d="M4 8h8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                  </svg>
                  Scale All -1
                </button>
                <button
                  className="btn btn-ghost"
                  onClick={async () => {
                    for (const dep of deployments) {
                      if (dep.replicas > 1) {
                        await scaleDeployment(dep.name, 1);
                      }
                    }
                    refresh();
                  }}
                  disabled={deployments.every(d => d.replicas <= 1)}
                >
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <circle cx="8" cy="8" r="3" stroke="currentColor" strokeWidth="1.5" />
                  </svg>
                  Scale All → 1
                </button>
                <button
                  className="btn btn-ghost btn-danger"
                  onClick={async () => {
                    if (window.confirm('Stop all NIM instances? This will scale all deployments to 0.')) {
                      for (const dep of deployments) {
                        await scaleDeployment(dep.name, 0);
                      }
                      refresh();
                    }
                  }}
                  disabled={deployments.every(d => d.replicas === 0)}
                >
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <rect x="4" y="4" width="8" height="8" fill="currentColor" />
                  </svg>
                  Stop All NIMs
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>,
    document.body
  );
}
