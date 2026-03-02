// NIM endpoint definitions

export type GpuType = 'H200' | 'B200' | 'RTX 6000' | 'L40S';

export interface NimEndpoint {
  id: string;
  name: string;
  category: 'llm' | 'structure' | 'molecule' | 'docking' | 'utility' | 'design';
  port: number;
  path: string;
  healthPath: string;
  description: string;
  status: 'ready' | 'not-ready' | 'checking' | 'unknown';
  required: boolean;
  gpu: GpuType;
  gpuCount?: number;
}

export const NIM_ENDPOINTS: NimEndpoint[] = [
  // LLM
  {
    id: 'nemotron',
    name: 'Nemotron-3-Nano',
    category: 'llm',
    port: 8014,
    path: '/v1/chat/completions',
    healthPath: '/v1/health/ready',
    description: 'Reasoning LLM for planning and narration',
    status: 'unknown',
    required: true,
    gpu: 'H200',
    gpuCount: 1,
  },

  // Structure Prediction - User can choose between these
  {
    id: 'openfold3',
    name: 'OpenFold3',
    category: 'structure',
    port: 8000,
    path: '/v1/biology/openfold/openfold3/predict',
    healthPath: '/v1/health/ready',
    description: 'Next-gen structure prediction',
    status: 'unknown',
    required: true,
    gpu: 'H200',
    gpuCount: 1,
  },
  {
    id: 'boltz2',
    name: 'Boltz2',
    category: 'structure',
    port: 8001,
    path: '/v1/biology/mit/boltz2/predict',
    healthPath: '/v1/health/ready',
    description: 'Fast structure prediction model',
    status: 'unknown',
    required: true,
    gpu: 'B200',
    gpuCount: 1,
  },
  {
    id: 'openfold2',
    name: 'OpenFold2',
    category: 'structure',
    port: 8004,
    path: '/v1/biology/openfold/openfold2/predict-structure-from-msa-and-template',
    healthPath: '/v1/health/ready',
    description: 'Structure prediction with MSA + template',
    status: 'unknown',
    required: true,
    gpu: 'H200',
    gpuCount: 1,
  },

  // Molecule Generation
  {
    id: 'genmol',
    name: 'GenMol',
    category: 'molecule',
    port: 8005,
    path: '/v1/biology/nvidia/genmol/generate',
    healthPath: '/v1/health/ready',
    description: 'Generate candidate molecules',
    status: 'unknown',
    required: true,
    gpu: 'RTX 6000',
    gpuCount: 1,
  },
  {
    id: 'molmim',
    name: 'MolMIM',
    category: 'molecule',
    port: 8006,
    path: '/generate',
    healthPath: '/v1/health/ready',
    description: 'Generate molecules around input SMILES',
    status: 'unknown',
    required: false,
    gpu: 'RTX 6000',
    gpuCount: 1,
  },

  // Docking
  {
    id: 'diffdock',
    name: 'DiffDock',
    category: 'docking',
    port: 8007,
    path: '/molecular-docking/diffdock/generate',
    healthPath: '/v1/health/ready',
    description: 'Molecular docking pose prediction',
    status: 'unknown',
    required: true,
    gpu: 'B200',
    gpuCount: 1,
  },

  // Utilities (optional)
  {
    id: 'msa-search',
    name: 'MSA Search',
    category: 'utility',
    port: 8003,
    path: '/v1/biology/colabfold/msa-search/predict',
    healthPath: '/v1/health/ready',
    description: 'Multiple sequence alignment (for OpenFold2)',
    status: 'unknown',
    required: false,
    gpu: 'RTX 6000',
    gpuCount: 1,
  },
  {
    id: 'evo2',
    name: 'Evo2-40B',
    category: 'utility',
    port: 8002,
    path: '/biology/arc/evo2/generate',
    healthPath: '/v1/health/ready',
    description: 'DNA/RNA foundation model',
    status: 'unknown',
    required: false,
    gpu: 'H200',
    gpuCount: 2,
  },

  // Protein Design
  {
    id: 'proteinmpnn',
    name: 'ProteinMPNN',
    category: 'design',
    port: 8009,
    path: '/biology/ipd/proteinmpnn/predict',
    healthPath: '/v1/health/ready',
    description: 'Design protein sequences for given structures',
    status: 'unknown',
    required: false,
    gpu: 'L40S',
    gpuCount: 1,
  },
  {
    id: 'rfdiffusion',
    name: 'RFDiffusion',
    category: 'design',
    port: 8010,
    path: '/biology/ipd/rfdiffusion/generate',
    healthPath: '/v1/health/ready',
    description: 'De novo protein structure generation',
    status: 'unknown',
    required: false,
    gpu: 'L40S',
    gpuCount: 1,
  },
];

// Structure models available for selection
export const STRUCTURE_MODELS = [
  {
    id: 'boltz2',
    name: 'Boltz2',
    description: 'Best accuracy on this deployment. Fast inference with excellent pLDDT scores.',
    badge: 'Recommended',
    port: 8001,
  },
  {
    id: 'openfold3',
    name: 'OpenFold3',
    description: 'Next-gen structure prediction. May require MSA search for best results.',
    badge: 'Experimental',
    port: 8000,
  },
  {
    id: 'openfold2',
    name: 'OpenFold2',
    description: 'High accuracy with MSA + template input. Best for well-characterized proteins.',
    badge: 'Accurate',
    port: 8004,
  },
];

export const getRequiredEndpoints = (): NimEndpoint[] => {
  return NIM_ENDPOINTS.filter((e) => e.required);
};

export const getEndpointsByCategory = (
  category: NimEndpoint['category']
): NimEndpoint[] => {
  return NIM_ENDPOINTS.filter((e) => e.category === category);
};

export const getEndpointById = (id: string): NimEndpoint | undefined => {
  return NIM_ENDPOINTS.find((e) => e.id === id);
};

export const getStructureModels = () => STRUCTURE_MODELS;
