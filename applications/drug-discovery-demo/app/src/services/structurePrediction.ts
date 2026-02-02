// Structure prediction API service

import { buildNimUrl } from './nimApi';

export interface StructurePredictionResult {
  structure: string; // PDB or CIF/mmCIF content
  format: 'pdb' | 'cif' | 'mmcif';
  confidenceScore: number;
  plddt: number;
  ptm: number;
  modelUsed: string;
  elapsedTime?: number; // Time in milliseconds
}

export interface ModelRequestBody {
  modelId: 'openfold3' | 'boltz2' | 'openfold2';
  endpoint: string;
  body: Record<string, unknown>;
}

/**
 * Create a simple CSV format MSA with just the query sequence
 * Format: "key,sequence\n-1,SEQUENCE"
 */
export function createCsvMsa(sequence: string): string {
  return `key,sequence\n-1,${sequence}`;
}

/**
 * Create a simple A3M format MSA with just the query sequence
 */
export function createA3mMsa(sequence: string): string {
  return `>query\n${sequence}`;
}

/**
 * Build request body for OpenFold3
 * Note: Uses a3m format with 'main' db which performs better than csv with 'main_db'
 * Note: Real MSA makes OpenFold3 worse - use single-sequence MSA only
 */
export function buildOpenFold3Request(sequence: string): Record<string, unknown> {
  const a3mMsa = createA3mMsa(sequence);
  return {
    inputs: [
      {
        input_id: 'prediction_1',
        molecules: [
          {
            type: 'protein',
            id: 'A',
            sequence: sequence,
            msa: {
              main: {
                a3m: {
                  alignment: a3mMsa,
                  format: 'a3m',
                },
              },
            },
          },
        ],
        diffusion_samples: 1,
        output_format: 'cif',
      },
    ],
  };
}

/**
 * Build request body for Boltz2
 */
export function buildBoltz2Request(sequence: string): Record<string, unknown> {
  return {
    polymers: [
      {
        molecule_type: 'protein',
        sequence: sequence,
        cyclic: false,
      },
    ],
    recycling_steps: 3,
    sampling_steps: 50,
    diffusion_samples: 1,
    step_scale: 1.638,
    output_format: 'mmcif',
  };
}

/**
 * Build request body for OpenFold2
 * Note: OpenFold2 uses 'alignments' not 'msa'
 */
export function buildOpenFold2Request(sequence: string): Record<string, unknown> {
  const msaContent = createA3mMsa(sequence);
  return {
    sequence: sequence,
    alignments: {
      uniref90: {
        a3m: {
          alignment: msaContent,
          format: 'a3m',
        },
      },
    },
    selected_models: [1, 2, 3, 4, 5],
    output_format: 'cif',
  };
}

/**
 * Get all model request bodies for parallel execution
 */
export function getAllModelRequests(gatewayUrl: string, sequence: string): ModelRequestBody[] {
  return [
    {
      modelId: 'openfold3',
      endpoint: buildNimUrl(gatewayUrl, 8000, '/biology/openfold/openfold3/predict'),
      body: buildOpenFold3Request(sequence),
    },
    {
      modelId: 'boltz2',
      endpoint: buildNimUrl(gatewayUrl, 8001, '/biology/mit/boltz2/predict'),
      body: buildBoltz2Request(sequence),
    },
    {
      modelId: 'openfold2',
      endpoint: buildNimUrl(gatewayUrl, 8004, '/biology/openfold/openfold2/predict-structure-from-msa-and-template'),
      body: buildOpenFold2Request(sequence),
    },
  ];
}

/**
 * Predict structure using OpenFold3
 * Simple interface that takes a protein sequence
 */
export async function predictWithOpenFold3(
  gatewayUrl: string,
  sequence: string,
  options: {
    outputFormat?: 'pdb' | 'cif';
    diffusionSamples?: number;
  } = {}
): Promise<StructurePredictionResult> {
  const { outputFormat = 'cif' } = options;

  const url = buildNimUrl(gatewayUrl, 8000, '/biology/openfold/openfold3/predict');

  // OpenFold3 requires MSA - provide a self-MSA with just the query sequence
  // Note: a3m format with 'main' db performs better than csv with 'main_db'
  // Note: Real MSA makes OpenFold3 worse - use single-sequence MSA only
  const a3mMsa = createA3mMsa(sequence);

  const requestBody = {
    inputs: [
      {
        input_id: 'prediction_1',
        molecules: [
          {
            type: 'protein',
            id: 'A',
            sequence: sequence,
            msa: {
              main: {
                a3m: {
                  alignment: a3mMsa,
                  format: 'a3m',
                },
              },
            },
          },
        ],
        diffusion_samples: 1,
        output_format: outputFormat,
      },
    ],
  };

  let response: Response;
  try {
    response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(requestBody),
    });
  } catch (networkError) {
    const message = networkError instanceof Error ? networkError.message : 'Unknown error';
    throw new Error(`OpenFold3 service unavailable: ${message}. The service may be down or restarting.`);
  }

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`OpenFold3 prediction failed: ${response.status} - ${errorText}`);
  }

  const data = await response.json();
  const output = data.outputs?.[0];
  const structureWithScores = output?.structures_with_scores?.[0];

  if (!structureWithScores) {
    throw new Error('No structure returned from OpenFold3');
  }

  return {
    structure: structureWithScores.structure,
    format: structureWithScores.format,
    confidenceScore: structureWithScores.confidence_score,
    plddt: structureWithScores.complex_plddt_score,
    ptm: structureWithScores.ptm_score,
    modelUsed: 'OpenFold3',
  };
}

/**
 * Predict structure using Boltz2
 */
export async function predictWithBoltz2(
  gatewayUrl: string,
  sequence: string,
  options: {
    recyclingSteps?: number;
    samplingSteps?: number;
    diffusionSamples?: number;
  } = {}
): Promise<StructurePredictionResult> {
  const { recyclingSteps = 3, samplingSteps = 50, diffusionSamples = 1 } = options;

  const url = buildNimUrl(gatewayUrl, 8001, '/biology/mit/boltz2/predict');

  const requestBody = {
    polymers: [
      {
        molecule_type: 'protein',
        sequence: sequence,
        cyclic: false,
      },
    ],
    recycling_steps: recyclingSteps,
    sampling_steps: samplingSteps,
    diffusion_samples: diffusionSamples,
    step_scale: 1.638,
    output_format: 'mmcif',
  };

  let response: Response;
  try {
    response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(requestBody),
    });
  } catch (networkError) {
    const message = networkError instanceof Error ? networkError.message : 'Unknown error';
    throw new Error(`Boltz2 service unavailable: ${message}. The service may be down or restarting.`);
  }

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Boltz2 prediction failed: ${response.status} - ${errorText}`);
  }

  const data = await response.json();

  // Boltz2 response structure:
  // - structures: [{structure: "...", format: "...", name: "...", source: "..."}]
  // - confidence_scores: [0.77...]
  // - ptm_scores: [0.62...]
  // - complex_plddt_scores: [0.80...]
  const structure = data.structures?.[0]?.structure || '';
  const confidenceScore = data.confidence_scores?.[0] ?? 0;
  const ptmScore = data.ptm_scores?.[0] ?? 0;
  const plddtScore = data.complex_plddt_scores?.[0] ?? 0;

  if (!structure) {
    throw new Error('No structure returned from Boltz2');
  }

  return {
    structure: structure,
    format: 'mmcif',
    confidenceScore: confidenceScore,
    plddt: plddtScore * 100, // Scale to 0-100 range
    ptm: ptmScore,
    modelUsed: 'Boltz2',
  };
}

/**
 * Predict structure using OpenFold2
 * Note: OpenFold2 requires MSA and templates for best results
 */
export async function predictWithOpenFold2(
  gatewayUrl: string,
  sequence: string,
  msa?: string,
  options: {
    outputFormat?: 'pdb' | 'cif';
  } = {}
): Promise<StructurePredictionResult> {
  const { outputFormat = 'cif' } = options;

  // OpenFold2 requires MSA - if not provided, we'll create a simple single-sequence MSA in A3M format
  const msaContent = msa || createA3mMsa(sequence);

  const url = buildNimUrl(gatewayUrl, 8004, '/biology/openfold/openfold2/predict-structure-from-msa-and-template');

  const requestBody = {
    sequence: sequence,
    alignments: {
      uniref90: {
        a3m: {
          alignment: msaContent,
          format: 'a3m',
        },
      },
    },
    selected_models: [1, 2, 3, 4, 5],
    output_format: outputFormat,
  };

  let response: Response;
  try {
    response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(requestBody),
    });
  } catch (networkError) {
    const message = networkError instanceof Error ? networkError.message : 'Unknown error';
    throw new Error(`OpenFold2 service unavailable: ${message}. The service may be down or restarting.`);
  }

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`OpenFold2 prediction failed: ${response.status} - ${errorText}`);
  }

  const data = await response.json();

  // OpenFold2 response structure:
  // - structures_in_ranked_order: [{structure: "...", format: "pdb", confidence: 38.7, rank_by_confidence: 0}]
  // - input_id: "..."
  // - metrics: {}
  const rankedStructure = data.structures_in_ranked_order?.[0];
  const structure = rankedStructure?.structure || '';
  const confidence = rankedStructure?.confidence ?? 0;
  const format = rankedStructure?.format || 'pdb';

  if (!structure) {
    throw new Error('No structure returned from OpenFold2');
  }

  return {
    structure: structure,
    format: format as 'pdb' | 'cif' | 'mmcif',
    confidenceScore: confidence / 100, // Normalize to 0-1 range
    plddt: confidence, // OpenFold2 uses confidence as the pLDDT-like metric
    ptm: 0, // OpenFold2 doesn't return pTM in this endpoint
    modelUsed: 'OpenFold2',
  };
}

/**
 * Generic predict function that routes to the appropriate model
 */
export async function predictStructure(
  gatewayUrl: string,
  sequence: string,
  modelId: 'openfold3' | 'boltz2' | 'openfold2'
): Promise<StructurePredictionResult> {
  switch (modelId) {
    case 'openfold3':
      return predictWithOpenFold3(gatewayUrl, sequence);
    case 'boltz2':
      return predictWithBoltz2(gatewayUrl, sequence);
    case 'openfold2':
      return predictWithOpenFold2(gatewayUrl, sequence);
    default:
      throw new Error(`Unknown model: ${modelId}`);
  }
}

/**
 * Result from a parallel prediction run
 */
export interface ParallelPredictionResult {
  modelId: 'openfold3' | 'boltz2' | 'openfold2';
  status: 'success' | 'error' | 'pending';
  result?: StructurePredictionResult;
  error?: string;
  elapsedTime?: number;
}

/**
 * Run prediction with a custom request body
 */
export async function predictWithCustomBody(
  endpoint: string,
  body: Record<string, unknown>,
  modelId: 'openfold3' | 'boltz2' | 'openfold2'
): Promise<StructurePredictionResult> {
  const startTime = Date.now();

  let response: Response;
  try {
    response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    });
  } catch (networkError) {
    const message = networkError instanceof Error ? networkError.message : 'Unknown error';
    throw new Error(`Service unavailable: ${message}`);
  }

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Prediction failed: ${response.status} - ${errorText}`);
  }

  const data = await response.json();
  const elapsedTime = Date.now() - startTime;

  // Parse response based on model
  if (modelId === 'openfold3') {
    const output = data.outputs?.[0];
    const structureWithScores = output?.structures_with_scores?.[0];
    if (!structureWithScores) {
      throw new Error('No structure returned from OpenFold3');
    }
    return {
      structure: structureWithScores.structure,
      format: structureWithScores.format,
      confidenceScore: structureWithScores.confidence_score,
      plddt: structureWithScores.complex_plddt_score,
      ptm: structureWithScores.ptm_score,
      modelUsed: 'OpenFold3',
      elapsedTime,
    };
  } else if (modelId === 'boltz2') {
    const structure = data.structures?.[0]?.structure || '';
    if (!structure) {
      throw new Error('No structure returned from Boltz2');
    }
    return {
      structure,
      format: 'mmcif',
      confidenceScore: data.confidence_scores?.[0] ?? 0,
      plddt: (data.complex_plddt_scores?.[0] ?? 0) * 100,
      ptm: data.ptm_scores?.[0] ?? 0,
      modelUsed: 'Boltz2',
      elapsedTime,
    };
  } else {
    // OpenFold2
    const rankedStructure = data.structures_in_ranked_order?.[0];
    const structure = rankedStructure?.structure || '';
    if (!structure) {
      throw new Error('No structure returned from OpenFold2');
    }
    const confidence = rankedStructure?.confidence ?? 0;
    return {
      structure,
      format: rankedStructure?.format || 'pdb',
      confidenceScore: confidence / 100,
      plddt: confidence,
      ptm: 0,
      modelUsed: 'OpenFold2',
      elapsedTime,
    };
  }
}

/**
 * Run all models in parallel with custom request bodies
 */
export async function predictAllModelsParallel(
  requests: ModelRequestBody[]
): Promise<ParallelPredictionResult[]> {
  const promises = requests.map(async (req): Promise<ParallelPredictionResult> => {
    const startTime = Date.now();
    try {
      const result = await predictWithCustomBody(req.endpoint, req.body, req.modelId);
      return {
        modelId: req.modelId,
        status: 'success',
        result,
        elapsedTime: Date.now() - startTime,
      };
    } catch (error) {
      return {
        modelId: req.modelId,
        status: 'error',
        error: error instanceof Error ? error.message : 'Unknown error',
        elapsedTime: Date.now() - startTime,
      };
    }
  });

  return Promise.all(promises);
}
