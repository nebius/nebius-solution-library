// Molecular similarity calculations using OpenChemLib
import { Molecule, SSSearcherWithIndex } from 'openchemlib';

/**
 * Result of a similarity comparison
 */
export interface SimilarityResult {
  smiles: string;
  similarity: number; // 0-1 Tanimoto coefficient
  rank: number;
}

/**
 * Result of rediscovery analysis
 */
export interface RediscoveryResult {
  referenceSmiles: string;
  referenceName: string;
  similarities: SimilarityResult[];
  bestMatch: SimilarityResult | null;
  exactMatch: boolean; // True if SMILES matches exactly
}

/**
 * Calculate fingerprint-based Tanimoto similarity between two molecules
 * Uses the SSSearcherWithIndex fingerprints from OpenChemLib
 */
export function calculateSimilarity(smiles1: string, smiles2: string): number {
  try {
    // Parse SMILES strings into molecules
    const mol1 = Molecule.fromSmiles(smiles1);
    const mol2 = Molecule.fromSmiles(smiles2);

    if (!mol1 || !mol2) {
      return 0;
    }

    // Get fingerprint indices for both molecules
    const fp1 = mol1.getIndex();
    const fp2 = mol2.getIndex();

    if (!fp1 || !fp2 || fp1.length === 0 || fp2.length === 0) {
      return 0;
    }

    // Use OpenChemLib's built-in Tanimoto similarity
    return SSSearcherWithIndex.getSimilarityTanimoto(fp1, fp2);
  } catch (error) {
    console.error('Error calculating similarity:', error);
    return 0;
  }
}

/**
 * Normalize SMILES for comparison (canonical form)
 */
export function canonicalizeSmiles(smiles: string): string {
  try {
    const mol = Molecule.fromSmiles(smiles);
    if (!mol) return smiles;
    return mol.toSmiles();
  } catch {
    return smiles;
  }
}

/**
 * Check if two SMILES represent the same molecule
 */
export function areSameMolecule(smiles1: string, smiles2: string): boolean {
  try {
    const canonical1 = canonicalizeSmiles(smiles1);
    const canonical2 = canonicalizeSmiles(smiles2);
    return canonical1 === canonical2;
  } catch {
    return smiles1 === smiles2;
  }
}

/**
 * Calculate similarities between a reference molecule and a list of candidates
 */
export function calculateBatchSimilarity(
  referenceSmiles: string,
  candidateSmiles: string[]
): SimilarityResult[] {
  const results: SimilarityResult[] = [];
  const canonicalRef = canonicalizeSmiles(referenceSmiles);

  for (const smiles of candidateSmiles) {
    const similarity = calculateSimilarity(referenceSmiles, smiles);
    const canonicalCandidate = canonicalizeSmiles(smiles);
    const isExactMatch = canonicalRef === canonicalCandidate;

    results.push({
      smiles,
      similarity: isExactMatch ? 1.0 : similarity,
      rank: 0, // Will be set after sorting
    });
  }

  // Sort by similarity descending
  results.sort((a, b) => b.similarity - a.similarity);

  // Assign ranks
  results.forEach((r, i) => {
    r.rank = i + 1;
  });

  return results;
}

/**
 * Perform full rediscovery analysis
 */
export function analyzeRediscovery(
  referenceSmiles: string,
  referenceName: string,
  candidateSmiles: string[]
): RediscoveryResult {
  const similarities = calculateBatchSimilarity(referenceSmiles, candidateSmiles);

  const bestMatch = similarities.length > 0 ? similarities[0] : null;
  const canonicalRef = canonicalizeSmiles(referenceSmiles);
  const exactMatch = similarities.some(
    (s) => canonicalizeSmiles(s.smiles) === canonicalRef
  );

  return {
    referenceSmiles,
    referenceName,
    similarities,
    bestMatch,
    exactMatch,
  };
}

/**
 * Get molecular properties for display
 */
export interface MolecularProperties {
  molecularWeight: number;
  atomCount: number;
  bondCount: number;
  ringCount: number;
  formula: string;
}

export function getMolecularProperties(smiles: string): MolecularProperties | null {
  try {
    const mol = Molecule.fromSmiles(smiles);
    if (!mol) return null;

    const formula = mol.getMolecularFormula();
    return {
      molecularWeight: formula.relativeWeight,
      atomCount: mol.getAtoms(),
      bondCount: mol.getBonds(),
      ringCount: mol.getRingSet().getSize(),
      formula: formula.formula,
    };
  } catch {
    return null;
  }
}

/**
 * Get similarity level category
 */
export function getSimilarityLevel(similarity: number): 'exact' | 'high' | 'medium' | 'low' {
  if (similarity >= 0.99) return 'exact';
  if (similarity >= 0.7) return 'high';
  if (similarity >= 0.4) return 'medium';
  return 'low';
}

/**
 * Format similarity as percentage
 */
export function formatSimilarity(similarity: number): string {
  return `${(similarity * 100).toFixed(1)}%`;
}
