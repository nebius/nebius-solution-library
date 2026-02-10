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
  const gpuLabel = labels['nvidia.com/gpu.product'] ||
                   labels['nvidia.com/gpu-product'] ||
                   labels['gpu-type'] || '';

  const gpuLower = gpuLabel.toLowerCase();
  // Currently the cluster only has B200 GPUs
  if (gpuLower.includes('b200')) return 'B200';

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
      const gpuReq = NIM_GPU_REQUIREMENTS[nimId] || { type: 'H200' as GpuType, count: 1 };

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

      deployments.push({
        name: k8sName,
        nimId,
        displayName: NIM_DISPLAY_NAMES[nimId] || nimId,
        replicas,
        availableReplicas,
        readyReplicas,
        gpuType: gpuReq.type,
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
      totalGpus: { B200: 0 },
      usedGpus: { B200: 0 },
      availableGpus: { B200: 0 },
    };
  }

  try {
    const res = await fetch('/api/k8s/nodes');
    const data = await res.json();

    const nodes: K8sNode[] = [];
    const totalGpus: Record<GpuType, number> = { B200: 0 };

    for (const item of data.items || []) {
      const name = item.metadata?.name || '';
      const labels = item.metadata?.labels || {};
      const allocatable = item.status?.allocatable || {};
      const conditions = item.status?.conditions || [];

      const gpuType = detectGpuType(labels);
      const gpuCount = parseInt(allocatable['nvidia.com/gpu'] || '0', 10);

      const readyCondition = conditions.find((c: { type: string }) => c.type === 'Ready');
      const status = readyCondition?.status === 'True' ? 'Ready' : 'NotReady';

      if (gpuType && gpuCount > 0) {
        totalGpus[gpuType] += gpuCount;
      }

      nodes.push({
        name,
        gpuType,
        gpuCount,
        gpuAllocatable: gpuCount,
        status,
      });
    }

    // Calculate used GPUs from deployments
    const deployments = await getDeployments();
    const usedGpus: Record<GpuType, number> = { B200: 0 };

    for (const dep of deployments) {
      usedGpus[dep.gpuType] += dep.availableReplicas * dep.gpuCount;
    }

    const availableGpus: Record<GpuType, number> = {
      B200: totalGpus.B200 - usedGpus.B200,
    };

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
      totalGpus: { B200: 0 },
      usedGpus: { B200: 0 },
      availableGpus: { B200: 0 },
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
  const available = capacity.availableGpus[gpuReq.type];

  if (needed > available) {
    return {
      allowed: false,
      reason: `Not enough ${gpuReq.type} GPUs available (need ${needed}, have ${available})`,
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
        gpuType: 'B200', // Would need to parse from template
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
          gpuType: gpuType || 'B200',
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

