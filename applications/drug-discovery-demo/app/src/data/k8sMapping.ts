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

// GPU types available in the cluster
export type GpuType = 'B200';

// GPU requirements per NIM
export interface GpuRequirement {
  type: GpuType;
  count: number;
}

export const NIM_GPU_REQUIREMENTS: Record<string, GpuRequirement> = {
  'openfold3': { type: 'B200', count: 1 },
  'boltz2': { type: 'B200', count: 1 },
  'openfold2': { type: 'B200', count: 1 },
  'genmol': { type: 'B200', count: 1 },
  'molmim': { type: 'B200', count: 1 },
  'diffdock': { type: 'B200', count: 1 },
  'qwen3': { type: 'B200', count: 2 },
  'msa': { type: 'B200', count: 1 },
  'evo2': { type: 'B200', count: 2 },
  'proteinmpnn': { type: 'B200', count: 1 },
  'rfdiffusion': { type: 'B200', count: 1 },
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

// GPU type display colors
export const GPU_TYPE_COLORS: Record<GpuType, string> = {
  'B200': '#76b900',    // NVIDIA green
};

// GPU type display names
export const GPU_TYPE_NAMES: Record<GpuType, string> = {
  'B200': 'NVIDIA B200',
};
