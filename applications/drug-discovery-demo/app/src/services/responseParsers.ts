/**
 * Response Parsers
 *
 * Centralized response parsing for all NIM endpoints.
 * This consolidates parsing logic that was duplicated in:
 * - structurePrediction.ts
 * - agent.ts (execute_raw_request tool)
 *
 * ## Why Centralize?
 *
 * NIM API response formats can vary between versions and models.
 * By centralizing parsing, we:
 * 1. Handle format variations in one place
 * 2. Make it easier to adapt to API changes
 * 3. Reduce code duplication
 * 4. Improve testability
 *
 * ## Response Format Variations
 *
 * ### OpenFold3
 * - Old: `data.outputs[0].structures_with_scores[0]`
 * - New: `data.prediction_1.structures[0]`
 * - Fallback: `data.structures[0]`
 *
 * ### Boltz2
 * - `data.structures[0]` with separate score arrays
 *
 * ### OpenFold2
 * - `data.structures_in_ranked_order[0]`
 */

import type { StructurePredictionResult } from './structurePrediction';

/**
 * Generic structure response that can come from any model
 */
export interface RawStructureResponse {
  // OpenFold3 new format
  prediction_1?: {
    structures?: Array<{
      cif?: string;
      pdb?: string;
      structure?: string;
      metrics?: {
        confidence_score?: number;
        ranking_score?: number;
        avg_plddt?: number;
        complex_plddt_score?: number;
        ptm?: number;
        ptm_score?: number;
      };
    }>;
    metrics?: {
      confidence_score?: number;
      ranking_score?: number;
      avg_plddt?: number;
      complex_plddt_score?: number;
      ptm?: number;
      ptm_score?: number;
    };
  };

  // OpenFold3 old format
  outputs?: Array<{
    structures_with_scores?: Array<{
      structure: string;
      format?: 'pdb' | 'cif';
      confidence_score?: number;
      complex_plddt_score?: number;
      ptm_score?: number;
    }>;
  }>;

  // OpenFold3 fallback / generic
  structures?: Array<{
    cif?: string;
    pdb?: string;
    structure?: string;
    format?: string;
    source?: string;
    name?: string;
  }>;
  metrics?: {
    confidence_score?: number;
    avg_plddt?: number;
    ptm?: number;
  };

  // Boltz2 format
  confidence_scores?: number[];
  ptm_scores?: number[];
  complex_plddt_scores?: number[];

  // OpenFold2 format
  structures_in_ranked_order?: Array<{
    structure: string;
    format?: string;
    confidence?: number;
    rank_by_confidence?: number;
  }>;
  input_id?: string;
}

/**
 * Parse OpenFold3 response
 *
 * Handles multiple response formats:
 * - New format: prediction_1.structures[0]
 * - Old format: outputs[0].structures_with_scores[0]
 * - Fallback: structures[0]
 */
export function parseOpenFold3Response(data: RawStructureResponse): StructurePredictionResult {
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
 * Parse Boltz2 response
 *
 * Boltz2 response structure:
 * - structures: [{structure: "...", format: "...", name: "...", source: "..."}]
 * - confidence_scores: [0.77...]
 * - ptm_scores: [0.62...]
 * - complex_plddt_scores: [0.80...]
 */
export function parseBoltz2Response(data: RawStructureResponse): StructurePredictionResult {
  const structure = data.structures?.[0]?.structure || '';
  const confidenceScore = data.confidence_scores?.[0] ?? 0;
  const ptmScore = data.ptm_scores?.[0] ?? 0;
  const plddtScore = data.complex_plddt_scores?.[0] ?? 0;

  if (!structure) {
    throw new Error('No structure returned from Boltz2');
  }

  return {
    structure,
    format: 'cif',
    confidenceScore,
    plddt: plddtScore * 100, // Scale to 0-100 range
    ptm: ptmScore,
    modelUsed: 'Boltz2',
  };
}

/**
 * Parse OpenFold2 response
 *
 * OpenFold2 response structure:
 * - structures_in_ranked_order: [{structure: "...", format: "pdb", confidence: 38.7, rank_by_confidence: 0}]
 * - input_id: "..."
 * - metrics: {}
 */
export function parseOpenFold2Response(data: RawStructureResponse): StructurePredictionResult {
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
    structure,
    format,
    confidenceScore: confidence / 100, // Normalize to 0-1 range
    plddt: confidence, // OpenFold2 uses confidence as the pLDDT-like metric
    ptm: 0, // OpenFold2 doesn't return pTM in this endpoint
    modelUsed: 'OpenFold2',
  };
}

/**
 * Parse a structure response from any model
 *
 * @param data - Raw response data
 * @param modelId - Model identifier to determine parsing strategy
 */
export function parseStructureResponse(
  data: RawStructureResponse,
  modelId: 'openfold3' | 'boltz2' | 'openfold2'
): StructurePredictionResult {
  switch (modelId) {
    case 'openfold3':
      return parseOpenFold3Response(data);
    case 'boltz2':
      return parseBoltz2Response(data);
    case 'openfold2':
      return parseOpenFold2Response(data);
    default:
      throw new Error(`Unknown model: ${modelId}`);
  }
}

/**
 * Try to detect model from response structure and parse accordingly
 *
 * Useful when model is unknown (e.g., execute_raw_request tool)
 */
export function parseUnknownStructureResponse(data: unknown): StructurePredictionResult | null {
  const response = data as RawStructureResponse;

  // Try OpenFold3 formats
  if (response.prediction_1?.structures?.[0] ||
      response.outputs?.[0]?.structures_with_scores?.[0]) {
    try {
      return parseOpenFold3Response(response);
    } catch {
      // Fall through
    }
  }

  // Try Boltz2 format (has confidence_scores array)
  if (response.structures?.[0] && response.confidence_scores) {
    try {
      return parseBoltz2Response(response);
    } catch {
      // Fall through
    }
  }

  // Try OpenFold2 format
  if (response.structures_in_ranked_order?.[0]) {
    try {
      return parseOpenFold2Response(response);
    } catch {
      // Fall through
    }
  }

  // Couldn't parse as structure response
  return null;
}

/**
 * Check if a response contains structure data
 */
export function hasStructureData(data: unknown): boolean {
  const response = data as RawStructureResponse;
  return !!(
    response.prediction_1?.structures?.[0] ||
    response.outputs?.[0]?.structures_with_scores?.[0] ||
    (response.structures?.[0] && (response.confidence_scores || response.structures_in_ranked_order)) ||
    response.structures_in_ranked_order?.[0]
  );
}
