/**
 * Structure Prediction Service
 *
 * This module handles 3D protein structure prediction using multiple AI models:
 * - OpenFold3 (port 8000) - Latest generation, recommended for most cases
 * - Boltz2 (port 8001) - Fast inference, MIT model
 * - OpenFold2 (port 8004) - High accuracy with MSA input
 *
 * ## Request Formats
 *
 * Each model has its own request format, handled by dedicated builder functions:
 * - `buildOpenFold3Request()` - Supports homo-oligomers via multiple molecules
 * - `buildBoltz2Request()` - Simple polymer-based format
 * - `buildOpenFold2Request()` - Requires MSA alignment data
 *
 * ## Response Parsing
 *
 * Response formats vary by model and API version. This module handles:
 * - OpenFold3: `data.outputs[0].structures_with_scores[0]` (old) or `data.prediction_1.structures[0]` (new)
 * - Boltz2: `data.structures[0]` with separate score arrays
 * - OpenFold2: `data.structures_in_ranked_order[0]`
 *
 * ## Fallback Mechanism
 *
 * If the primary model fails, automatic fallback tries other models:
 * ```
 * openfold3 → boltz2 → openfold2
 * boltz2 → openfold3 → openfold2
 * openfold2 → boltz2 → openfold3
 * ```
 *
 * ## Homodimer Support
 *
 * For proteins that function as homodimers (e.g., COX-2):
 * ```typescript
 * predictStructure(url, sequence, 'openfold3', { numCopies: 2 })
 * ```
 * This creates two chains (A, B) with the same sequence.
 *
 * @see ARCHITECTURE.md for endpoint details
 * @see agent.ts for how this is called from the agent
 */

import { buildNimUrl } from './nimApi';
import { isDemoMode, demoPredictStructure } from './demoService';

export interface StructurePredictionResult {
  structure: string; // PDB or PDBx/mmCIF content
  format: 'pdb' | 'cif'; // 'cif' = PDBx/mmCIF format (standardized)
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
 * Uses the inputs array format with molecules and MSA
 * @param sequence - The protein sequence
 * @param numCopies - Number of copies (chains) for homo-oligomers (default: 1 for monomer)
 */
export function buildOpenFold3Request(sequence: string, numCopies = 1): Record<string, unknown> {
  // Generate chain IDs: A, B, C, ... based on number of copies
  const chainIds = Array.from({ length: numCopies }, (_, i) => String.fromCharCode(65 + i));

  // Create a molecule for each chain (homodimers have same sequence, different IDs)
  const molecules = chainIds.map((id) => ({
    type: 'protein',
    id: id,
    sequence: sequence,
    msa: {
      main: {
        a3m: {
          alignment: `>query\n${sequence}`,
          format: 'a3m',
        },
      },
    },
  }));

  return {
    inputs: [
      {
        input_id: 'prediction_1',
        molecules: molecules,
        diffusion_samples: 1,
        output_format: 'cif',
      },
    ],
  };
}

/**
 * Build request body for Boltz2
 * Note: Both Boltz2 and OpenFold3 produce PDBx/mmCIF with ModelCIF extensions.
 * Boltz2 requires 'mmcif' as output_format value.
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
 * @param numCopies - Number of chain copies for homo-oligomers (only applies to OpenFold3, default: 1)
 */
export function getAllModelRequests(gatewayUrl: string, sequence: string, numCopies = 1): ModelRequestBody[] {
  return [
    {
      modelId: 'openfold3',
      endpoint: buildNimUrl(gatewayUrl, 8000, '/biology/openfold/openfold3/predict'),
      body: buildOpenFold3Request(sequence, numCopies),
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
 * Uses the inputs array format with molecules and MSA
 * @param numCopies - Number of copies for homo-oligomers (default: 1 for monomer, use 2 for homodimer)
 */
export async function predictWithOpenFold3(
  gatewayUrl: string,
  sequence: string,
  options: {
    numCopies?: number;
  } = {}
): Promise<StructurePredictionResult> {
  const { numCopies = 1 } = options;

  const url = buildNimUrl(gatewayUrl, 8000, '/biology/openfold/openfold3/predict');

  // Use the validated request builder
  const requestBody = buildOpenFold3Request(sequence, numCopies);

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

  // Parse response - handle both old and new response formats
  let structure: string;
  let format: 'pdb' | 'cif';
  let confidenceScore: number;
  let plddt: number;
  let ptm: number;

  // New format: data.prediction_1.structures[0]
  if (data.prediction_1?.structures?.[0]) {
    const result = data.prediction_1.structures[0];
    structure = result.cif || result.pdb || result.structure || '';
    format = result.cif ? 'cif' : 'pdb';
    // Metrics might be at different levels
    const metrics = result.metrics || data.prediction_1.metrics || {};
    confidenceScore = metrics.confidence_score ?? metrics.ranking_score ?? 0;
    plddt = metrics.avg_plddt ?? metrics.complex_plddt_score ?? 0;
    ptm = metrics.ptm ?? metrics.ptm_score ?? 0;
  }
  // Old format: data.outputs[0].structures_with_scores[0]
  else if (data.outputs?.[0]?.structures_with_scores?.[0]) {
    const structureWithScores = data.outputs[0].structures_with_scores[0];
    structure = structureWithScores.structure;
    format = structureWithScores.format || 'cif';
    confidenceScore = structureWithScores.confidence_score ?? 0;
    plddt = structureWithScores.complex_plddt_score ?? 0;
    ptm = structureWithScores.ptm_score ?? 0;
  }
  // Fallback: try to find structure at root level
  else if (data.structures?.[0]) {
    const result = data.structures[0];
    structure = result.cif || result.pdb || result.structure || '';
    format = result.cif ? 'cif' : 'pdb';
    const metrics = data.metrics || {};
    confidenceScore = metrics.confidence_score ?? 0;
    plddt = metrics.avg_plddt ?? 0;
    ptm = metrics.ptm ?? 0;
  }
  else {
    console.error('OpenFold3 response structure:', JSON.stringify(data).substring(0, 1000));
    throw new Error('No structure returned from OpenFold3 - unexpected response format');
  }

  if (!structure) {
    throw new Error('No structure data in OpenFold3 response');
  }

  return {
    structure,
    format,
    confidenceScore,
    plddt,
    ptm,
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
    format: 'cif',
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
  const rawFormat = rankedStructure?.format || 'pdb';
  // Normalize 'mmcif' to 'cif' for consistency
  const format: 'pdb' | 'cif' = rawFormat === 'mmcif' ? 'cif' : (rawFormat === 'cif' ? 'cif' : 'pdb');

  if (!structure) {
    throw new Error('No structure returned from OpenFold2');
  }

  return {
    structure: structure,
    format,
    confidenceScore: confidence / 100, // Normalize to 0-1 range
    plddt: confidence, // OpenFold2 uses confidence as the pLDDT-like metric
    ptm: 0, // OpenFold2 doesn't return pTM in this endpoint
    modelUsed: 'OpenFold2',
  };
}

/**
 * Generic predict function that routes to the appropriate model
 * With automatic fallback to other models if the primary fails
 * @param numCopies - Number of chain copies for homo-oligomers (only applies to OpenFold3, default: 1)
 */
export async function predictStructure(
  gatewayUrl: string,
  sequence: string,
  modelId: 'openfold3' | 'boltz2' | 'openfold2',
  options: { enableFallback?: boolean; numCopies?: number } = {}
): Promise<StructurePredictionResult> {
  const { enableFallback = true, numCopies = 1 } = options;

  // Check for demo mode
  if (isDemoMode()) {
    return demoPredictStructure(sequence, modelId);
  }

  // Define fallback order for each model
  const fallbackOrder: Record<string, Array<'openfold3' | 'boltz2' | 'openfold2'>> = {
    openfold3: ['openfold3', 'boltz2', 'openfold2'],
    boltz2: ['boltz2', 'openfold3', 'openfold2'],
    openfold2: ['openfold2', 'boltz2', 'openfold3'],
  };

  const modelsToTry = enableFallback ? fallbackOrder[modelId] : [modelId];
  const errors: string[] = [];

  for (const model of modelsToTry) {
    try {
      switch (model) {
        case 'openfold3':
          return await predictWithOpenFold3(gatewayUrl, sequence, { numCopies });
        case 'boltz2':
          return await predictWithBoltz2(gatewayUrl, sequence);
        case 'openfold2':
          return await predictWithOpenFold2(gatewayUrl, sequence);
      }
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : 'Unknown error';
      errors.push(`${model}: ${errMsg}`);
      console.warn(`Structure prediction with ${model} failed, trying next model...`, errMsg);
      // Continue to next model in fallback list
    }
  }

  // All models failed
  throw new Error(`All structure prediction models failed:\n${errors.join('\n')}`);
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
    // Handle both old and new response formats
    let structure: string;
    let format: 'pdb' | 'cif';
    let confidenceScore: number;
    let plddt: number;
    let ptm: number;

    // New format: data.prediction_1.structures[0]
    if (data.prediction_1?.structures?.[0]) {
      const result = data.prediction_1.structures[0];
      structure = result.cif || result.pdb || result.structure || '';
      format = result.cif ? 'cif' : 'pdb';
      const metrics = result.metrics || data.prediction_1.metrics || {};
      confidenceScore = metrics.confidence_score ?? metrics.ranking_score ?? 0;
      plddt = metrics.avg_plddt ?? metrics.complex_plddt_score ?? 0;
      ptm = metrics.ptm ?? metrics.ptm_score ?? 0;
    }
    // Old format: data.outputs[0].structures_with_scores[0]
    else if (data.outputs?.[0]?.structures_with_scores?.[0]) {
      const structureWithScores = data.outputs[0].structures_with_scores[0];
      structure = structureWithScores.structure;
      format = structureWithScores.format || 'cif';
      confidenceScore = structureWithScores.confidence_score ?? 0;
      plddt = structureWithScores.complex_plddt_score ?? 0;
      ptm = structureWithScores.ptm_score ?? 0;
    }
    // Fallback: try to find structure at root level
    else if (data.structures?.[0]) {
      const result = data.structures[0];
      structure = result.cif || result.pdb || result.structure || '';
      format = result.cif ? 'cif' : 'pdb';
      const metrics = data.metrics || {};
      confidenceScore = metrics.confidence_score ?? 0;
      plddt = metrics.avg_plddt ?? 0;
      ptm = metrics.ptm ?? 0;
    }
    else {
      throw new Error('No structure returned from OpenFold3');
    }

    if (!structure) {
      throw new Error('No structure data in OpenFold3 response');
    }

    return {
      structure,
      format,
      confidenceScore,
      plddt,
      ptm,
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
      format: 'cif',
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
