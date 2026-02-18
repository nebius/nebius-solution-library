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
  const url = buildNimUrl(gatewayUrl, 8006, '/generate');

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
    .filter((m: { smiles?: string; score?: number }) =>
      m.smiles && m.smiles.length > 0 && isValidSmiles(m.smiles)
    )
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
 * Quick structural validation: balanced parens/brackets and paired ring digits.
 */
function isValidSmiles(smi: string): boolean {
  if (!smi || smi.length < 2) return false;
  let parenDepth = 0;
  let bracketDepth = 0;
  for (const ch of smi) {
    if (ch === '(') parenDepth++;
    else if (ch === ')') parenDepth--;
    else if (ch === '[') bracketDepth++;
    else if (ch === ']') bracketDepth--;
    if (parenDepth < 0 || bracketDepth < 0) return false;
  }
  if (parenDepth !== 0 || bracketDepth !== 0) return false;
  // Ring digits must come in pairs
  let inBracket = false;
  const ringCounts = new Map<string, number>();
  for (let i = 0; i < smi.length; i++) {
    const ch = smi[i];
    if (ch === '[') { inBracket = true; continue; }
    if (ch === ']') { inBracket = false; continue; }
    if (inBracket) continue;
    if (ch === '%' && i + 2 < smi.length && /^\d{2}$/.test(smi[i + 1] + smi[i + 2])) {
      const pair = smi[i + 1] + smi[i + 2];
      ringCounts.set(pair, (ringCounts.get(pair) || 0) + 1);
      i += 2;
      continue;
    }
    if (/\d/.test(ch)) {
      ringCounts.set(ch, (ringCounts.get(ch) || 0) + 1);
    }
  }
  for (const count of ringCounts.values()) {
    if (count % 2 !== 0) return false;
  }
  return true;
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
