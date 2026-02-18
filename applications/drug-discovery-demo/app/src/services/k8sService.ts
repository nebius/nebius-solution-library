/**
 * Kubernetes Service
 * Provides API for interacting with K8s cluster via the kubectl proxy
 */

import {
  K8S_TO_NIM,
  NIM_GPU_REQUIREMENTS,
  NIM_DISPLAY_NAMES,
  DEFAULT_NAMESPACE,
  type GpuType,
} from '../data/k8sMapping';

// Types

export interface K8sDeployment {
  name: string;
  nimId: string;
  displayName: string;
  replicas: number;
  availableReplicas: number;
  readyReplicas: number;
  gpuType: GpuType;
  gpuCount: number;
  status: 'healthy' | 'scaling' | 'degraded' | 'unavailable';
}

export interface K8sNode {
  name: string;
  gpuType: GpuType | null;
  gpuCount: number;
  gpuAllocatable: number;
  status: 'Ready' | 'NotReady';
}

export interface ClusterCapacity {
  connected: boolean;
  context?: string;
  nodes: K8sNode[];
  totalGpus: Record<GpuType, number>;
  usedGpus: Record<GpuType, number>;
  availableGpus: Record<GpuType, number>;
}

export interface K8sHealthCheck {
  connected: boolean;
  context?: string;
  error?: string;
}

export interface NodeGroup {
  id: string;
  name: string;
  nodeCount: number;
  gpuType: string;
  gpuPerNode: number;
  totalGpus: number;
}

// Helper to detect GPU type from node labels
function detectGpuType(labels: Record<string, string>): GpuType | null {
  // Check various label keys for GPU product info
  const gpuLabel = labels['nvidia.com/gpu.product'] ||
                   labels['nvidia.com/gpu-product'] ||
                   labels['gpu-type'] || '';

  // Also check instance type labels (e.g. "gpu-h200-sxm")
  const instanceType = labels['node.kubernetes.io/instance-type'] || '';
  const combined = `${gpuLabel} ${instanceType}`.toLowerCase();

  if (combined.includes('h200')) return 'H200';
  if (combined.includes('b200')) return 'B200';
  if (combined.includes('h100')) return 'H100';
  if (combined.includes('a100')) return 'A100';
  if (combined.includes('l40'))  return 'L40S';

  return null;
}

// API Functions

export async function checkK8sHealth(): Promise<K8sHealthCheck> {
  try {
    const res = await fetch('/api/k8s/health');
    const data = await res.json();
    return data;
  } catch (err) {
    return { connected: false, error: 'Failed to connect to kubectl proxy' };
  }
}

export async function getDeployments(namespace = DEFAULT_NAMESPACE): Promise<K8sDeployment[]> {
  try {
    const res = await fetch(`/api/k8s/deployments?namespace=${namespace}`);
    const data = await res.json();

    if (data.error) {
      console.error('K8s API error:', data.error);
      return [];
    }

    const deployments: K8sDeployment[] = [];

    for (const item of data.items || []) {
      const k8sName = item.metadata?.name || '';
      const nimId = K8S_TO_NIM[k8sName];

      // Only include known NIM deployments
      if (!nimId) continue;

      const spec = item.spec || {};
      const status = item.status || {};
      const gpuReq = NIM_GPU_REQUIREMENTS[nimId] || { count: 1 };

      const replicas = spec.replicas || 0;
      const availableReplicas = status.availableReplicas || 0;
      const readyReplicas = status.readyReplicas || 0;

      let deploymentStatus: K8sDeployment['status'] = 'healthy';
      if (availableReplicas === 0) {
        deploymentStatus = 'unavailable';
      } else if (availableReplicas < replicas) {
        deploymentStatus = 'scaling';
      } else if (readyReplicas < availableReplicas) {
        deploymentStatus = 'degraded';
      }

      // GPU type is determined at runtime from cluster nodes, not statically
      // Default to 'H200' — will be overridden when cluster data is available
      deployments.push({
        name: k8sName,
        nimId,
        displayName: NIM_DISPLAY_NAMES[nimId] || nimId,
        replicas,
        availableReplicas,
        readyReplicas,
        gpuType: 'H200',
        gpuCount: gpuReq.count,
        status: deploymentStatus,
      });
    }

    return deployments;
  } catch (err) {
    console.error('Failed to fetch deployments:', err);
    return [];
  }
}

export async function scaleDeployment(
  deploymentName: string,
  replicas: number,
  namespace = DEFAULT_NAMESPACE
): Promise<{ success: boolean; error?: string }> {
  try {
    const res = await fetch('/api/k8s/scale', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ deployment: deploymentName, replicas, namespace }),
    });

    const data = await res.json();
    return data;
  } catch (err) {
    return { success: false, error: 'Failed to scale deployment' };
  }
}

export async function getClusterCapacity(): Promise<ClusterCapacity> {
  const health = await checkK8sHealth();
  if (!health.connected) {
    return {
      connected: false,
      nodes: [],
      totalGpus: {},
      usedGpus: {},
      availableGpus: {},
    };
  }

  try {
    const [nodesRes, deployments] = await Promise.all([
      fetch('/api/k8s/nodes'),
      getDeployments(),
    ]);
    const data = await nodesRes.json();

    const nodes: K8sNode[] = [];
    const totalGpus: Record<GpuType, number> = {};

    for (const item of data.items || []) {
      const name = item.metadata?.name || '';
      const labels = item.metadata?.labels || {};
      const allocatable = item.status?.allocatable || {};
      const conditions = item.status?.conditions || [];

      const gpuType = detectGpuType(labels);
      const gpuCount = parseInt(allocatable['nvidia.com/gpu'] || '0', 10);

      const readyCondition = conditions.find((c: { type: string }) => c.type === 'Ready');
      const status = readyCondition?.status === 'True' ? 'Ready' : 'NotReady';

      // Resolved type: detected label or default to 'GPU' for unknown
      const resolvedType = gpuType || (gpuCount > 0 ? 'GPU' : null);

      if (gpuCount > 0 && resolvedType) {
        totalGpus[resolvedType] = (totalGpus[resolvedType] || 0) + gpuCount;
      }

      nodes.push({
        name,
        gpuType: resolvedType,
        gpuCount,
        gpuAllocatable: gpuCount,
        status,
      });
    }

    // Determine the dominant GPU type (most common in the cluster)
    const dominantGpuType = Object.entries(totalGpus)
      .sort((a, b) => b[1] - a[1])[0]?.[0] || 'GPU';

    // Update deployments with the actual detected GPU type
    for (const dep of deployments) {
      dep.gpuType = dominantGpuType;
    }

    // Calculate used GPUs from deployments
    const usedGpus: Record<GpuType, number> = {};
    for (const dep of deployments) {
      usedGpus[dep.gpuType] = (usedGpus[dep.gpuType] || 0) + dep.availableReplicas * dep.gpuCount;
    }

    const availableGpus: Record<GpuType, number> = {};
    for (const type of Object.keys(totalGpus)) {
      availableGpus[type] = Math.max(0, totalGpus[type] - (usedGpus[type] || 0));
    }

    return {
      connected: true,
      context: health.context,
      nodes,
      totalGpus,
      usedGpus,
      availableGpus,
    };
  } catch (err) {
    console.error('Failed to get cluster capacity:', err);
    return {
      connected: false,
      nodes: [],
      totalGpus: {},
      usedGpus: {},
      availableGpus: {},
    };
  }
}

// Check if scaling is safe (won't exceed capacity)
export async function canScale(
  nimId: string,
  newReplicas: number,
  currentReplicas: number
): Promise<{ allowed: boolean; reason?: string }> {
  if (newReplicas <= currentReplicas) {
    return { allowed: true };
  }

  const capacity = await getClusterCapacity();
  const gpuReq = NIM_GPU_REQUIREMENTS[nimId];

  if (!gpuReq) {
    return { allowed: false, reason: 'Unknown NIM type' };
  }

  const delta = newReplicas - currentReplicas;
  const needed = delta * gpuReq.count;

  // Sum all available GPUs across types
  const totalAvailable = Object.values(capacity.availableGpus).reduce((a, b) => a + b, 0);

  if (needed > totalAvailable) {
    return {
      allowed: false,
      reason: `Not enough GPUs available (need ${needed}, have ${totalAvailable})`,
    };
  }

  return { allowed: true };
}

// Node group functions

export async function getNodeGroups(): Promise<NodeGroup[]> {
  try {
    const res = await fetch('/api/k8s/nodegroups');
    const data = await res.json();

    if (data.error) {
      console.error('K8s API error:', data.error);
      return [];
    }

    // Handle MachineDeployments (cluster-api)
    if (data.type === 'machinedeployments' && data.data?.items) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      return data.data.items.map((md: any) => ({
        id: md.metadata?.name || '',
        name: md.metadata?.name || '',
        nodeCount: md.spec?.replicas || 0,
        gpuType: 'H200', // Would need to parse from template
        gpuPerNode: 8,
        totalGpus: (md.spec?.replicas || 0) * 8,
      }));
    }

    // Handle label-based node groups
    if (data.type === 'labels' && data.nodeGroups) {
      return Object.entries(data.nodeGroups).map(([name, info]) => {
        const { count, gpuType, gpuPerNode } = info as { count: number; gpuType: string; gpuPerNode: number };
        return {
          id: name,
          name,
          nodeCount: count,
          gpuType: gpuType || 'H200',
          gpuPerNode: gpuPerNode || 8,
          totalGpus: count * (gpuPerNode || 8),
        };
      });
    }

    return [];
  } catch (err) {
    console.error('Failed to fetch node groups:', err);
    return [];
  }
}

export interface ScaleNodeGroupResult {
  success: boolean;
  error?: string;
  traceId?: string;
  suggestion?: string;
}

export async function scaleNodeGroup(
  nodeGroupId: string,
  nodeCount: number
): Promise<ScaleNodeGroupResult> {
  try {
    const res = await fetch('/api/k8s/scale-nodegroup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nodeGroupId, nodeCount }),
    });

    const data = await res.json();
    return {
      success: data.success ?? false,
      error: data.error,
      traceId: data.traceId,
      suggestion: data.suggestion,
    };
  } catch (err) {
    return { success: false, error: 'Failed to connect to scaling service' };
  }
}

