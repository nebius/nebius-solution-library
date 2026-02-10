// Molecule generation API service

import { buildNimUrl } from './nimApi';

export interface GeneratedMolecule {
  smiles: string;
  score: number;
  isReference?: boolean; // True if this is the reference drug being "rediscovered"
}

export interface MoleculeGenerationResult {
  molecules: GeneratedMolecule[];
  modelUsed: string;
  elapsedTime: number;
}

export interface MolMIMRequest {
  smi: string;
  num_molecules?: number;
  particles?: number; // Must be >= num_molecules
  algorithm?: 'CMA-ES' | 'none';
  iterations?: number;
  min_similarity?: number;
  property_name?: 'QED' | 'plogP';
  scaled_radius?: number;
  minimize?: boolean;
}

/**
 * Build default MolMIM request
 * Note: particles must be >= num_molecules (API requirement)
 */
export function buildMolMIMRequest(
  seedSmiles: string,
  numMolecules: number = 30
): MolMIMRequest {
  return {
    smi: seedSmiles,
    num_molecules: numMolecules,
    particles: Math.max(numMolecules, 30), // Ensure particles >= num_molecules
    algorithm: 'none',
    scaled_radius: 1.2,
  };
}

/**
 * Generate molecules using MolMIM
 */
export async function generateWithMolMIM(
  gatewayUrl: string,
  request: MolMIMRequest
): Promise<MoleculeGenerationResult> {
  const startTime = Date.now();
  const url = buildNimUrl(gatewayUrl, 8006, '/biology/nvidia/molmim/generate');

  let response: Response;
  try {
    response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    });
  } catch (networkError) {
    const message = networkError instanceof Error ? networkError.message : 'Unknown error';
    throw new Error(`MolMIM service unavailable: ${message}`);
  }

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`MolMIM generation failed: ${response.status} - ${errorText}`);
  }

  const data = await response.json();
  const elapsedTime = Date.now() - startTime;

  if (!data.generated || !Array.isArray(data.generated)) {
    throw new Error('No molecules returned from MolMIM');
  }

  const molecules: GeneratedMolecule[] = data.generated
    .filter((m: { smiles?: string; score?: number }) => m.smiles && m.smiles.length > 0)
    .map((m: { smiles: string; score: number }) => ({
      smiles: m.smiles,
      score: m.score ?? 0,
    }));

  return {
    molecules,
    modelUsed: 'MolMIM',
    elapsedTime,
  };
}

/**
 * Sort molecules by score (descending)
 */
export function sortByScore(molecules: GeneratedMolecule[]): GeneratedMolecule[] {
  return [...molecules].sort((a, b) => b.score - a.score);
}

/**
 * Filter molecules by minimum score
 */
export function filterByMinScore(
  molecules: GeneratedMolecule[],
  minScore: number
): GeneratedMolecule[] {
  return molecules.filter(m => m.score >= minScore);
}
