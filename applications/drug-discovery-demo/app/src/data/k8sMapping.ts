/**
 * Kubernetes Deployment Mapping
 * Maps NIM endpoint IDs to K8s deployment names and resource requirements
 */

// Map NIM endpoint IDs to K8s deployment names
export const NIM_TO_K8S: Record<string, string> = {
  'openfold3': 'openfold3',
  'boltz2': 'boltz2',
  'openfold2': 'openfold2',
  'genmol': 'genmol',
  'molmim': 'molmim',
  'diffdock': 'diffdock',
  'qwen3': 'qwen3-next-80b-a3b-instruct',
  'msa': 'msa-search',
  'evo2': 'evo2-40b',
  'proteinmpnn': 'proteinmpnn',
  'rfdiffusion': 'rfdiffusion',
};

// Reverse mapping: K8s deployment names to NIM endpoint IDs
export const K8S_TO_NIM: Record<string, string> = Object.fromEntries(
  Object.entries(NIM_TO_K8S).map(([k, v]) => [v, k])
);

// GPU type is a string detected dynamically from node labels
export type GpuType = string;

// GPU requirements per NIM (count per replica)
export interface GpuRequirement {
  count: number;
}

export const NIM_GPU_REQUIREMENTS: Record<string, GpuRequirement> = {
  'openfold3': { count: 1 },
  'boltz2': { count: 1 },
  'openfold2': { count: 1 },
  'genmol': { count: 1 },
  'molmim': { count: 1 },
  'diffdock': { count: 1 },
  'qwen3': { count: 2 },
  'msa': { count: 1 },
  'evo2': { count: 2 },
  'proteinmpnn': { count: 1 },
  'rfdiffusion': { count: 1 },
};

// Display names for NIMs
export const NIM_DISPLAY_NAMES: Record<string, string> = {
  'openfold3': 'OpenFold3',
  'boltz2': 'Boltz2',
  'openfold2': 'OpenFold2',
  'genmol': 'GenMol',
  'molmim': 'MolMIM',
  'diffdock': 'DiffDock',
  'qwen3': 'Qwen3-80B',
  'msa': 'MSA Search',
  'evo2': 'Evo2-40B',
  'proteinmpnn': 'ProteinMPNN',
  'rfdiffusion': 'RFDiffusion',
};

// NIMs that can be run in parallel (for structure prediction, etc.)
export const PARALLELIZABLE_NIMS = ['openfold3', 'boltz2', 'openfold2'];

// Default namespace for NIM deployments
export const DEFAULT_NAMESPACE = 'nims';

/**
 * Derive a display-friendly GPU name from a detected type string.
 * e.g. "H200" → "NVIDIA H200 SXM", "B200" → "NVIDIA B200", "H100" → "NVIDIA H100"
 */
export function getGpuDisplayName(gpuType: string): string {
  const upper = gpuType.toUpperCase();
  if (upper.includes('H200')) return 'NVIDIA H200 SXM';
  if (upper.includes('B200')) return 'NVIDIA B200';
  if (upper.includes('H100')) return 'NVIDIA H100';
  if (upper.includes('A100')) return 'NVIDIA A100';
  if (upper.includes('L40')) return 'NVIDIA L40S';
  if (upper.includes('RTX')) return `NVIDIA ${upper}`;
  return `GPU (${gpuType})`;
}

/**
 * Get a color for a GPU type for the capacity bars.
 */
export function getGpuColor(gpuType: string): string {
  const upper = gpuType.toUpperCase();
  if (upper.includes('H200')) return '#76b900';  // NVIDIA green
  if (upper.includes('B200')) return '#1a8cff';  // blue
  if (upper.includes('H100')) return '#ff6b00';  // orange
  if (upper.includes('A100')) return '#9b59b6';  // purple
  if (upper.includes('L40')) return '#e67e22';   // amber
  return '#76b900'; // default NVIDIA green
}
