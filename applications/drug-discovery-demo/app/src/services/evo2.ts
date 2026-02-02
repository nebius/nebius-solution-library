// Evo2-40B DNA/RNA Foundation Model API service

import { buildNimUrl } from './nimApi';

export interface Evo2GenerationResult {
  sequences: string[];
  originalSequence: string;
}

export interface Evo2AnalysisResult {
  mutations: MutationSuggestion[];
  conservedRegions: Region[];
  variableRegions: Region[];
}

export interface MutationSuggestion {
  position: number;
  originalAa: string;
  suggestedAa: string;
  rationale: string;
  confidence: number;
}

export interface Region {
  start: number;
  end: number;
  description: string;
}

/**
 * Convert a protein sequence to DNA using the standard codon table
 * Uses the most common codon for each amino acid
 */
export function proteinToDna(proteinSequence: string): string {
  const codonTable: Record<string, string> = {
    'A': 'GCT', 'R': 'CGT', 'N': 'AAT', 'D': 'GAT', 'C': 'TGT',
    'Q': 'CAA', 'E': 'GAA', 'G': 'GGT', 'H': 'CAT', 'I': 'ATT',
    'L': 'CTT', 'K': 'AAA', 'M': 'ATG', 'F': 'TTT', 'P': 'CCT',
    'S': 'TCT', 'T': 'ACT', 'W': 'TGG', 'Y': 'TAT', 'V': 'GTT',
    '*': 'TAA', // Stop codon
  };

  return proteinSequence
    .toUpperCase()
    .split('')
    .map(aa => codonTable[aa] || 'NNN')
    .join('');
}

/**
 * Generate DNA sequence variations using Evo2
 * Can be used for codon optimization or exploring sequence space
 */
export async function generateSequenceVariations(
  gatewayUrl: string,
  dnaSequence: string,
  options: {
    numVariations?: number;
    temperature?: number;
  } = {}
): Promise<Evo2GenerationResult> {
  const { numVariations = 3, temperature = 0.7 } = options;

  const url = buildNimUrl(gatewayUrl, 8002, '/biology/arc/evo2/generate');

  // Evo2 generates one sequence per call, so we run multiple calls
  const sequences: string[] = [];

  for (let i = 0; i < numVariations; i++) {
    const requestBody = {
      sequence: dnaSequence,
      temperature: temperature,
      top_k: 4,
      top_p: 0.95,
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
      throw new Error(`Evo2 service unavailable: ${message}. The service may be down or restarting.`);
    }

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Evo2 generation failed: ${response.status} - ${errorText}`);
    }

    const data = await response.json();
    if (data.sequence) {
      sequences.push(data.sequence);
    }
  }

  return {
    sequences,
    originalSequence: dnaSequence,
  };
}

/**
 * Use Evo2 to complete/extend a DNA sequence
 */
export async function extendSequence(
  gatewayUrl: string,
  dnaSequence: string,
  options: {
    temperature?: number;
  } = {}
): Promise<string> {
  const { temperature = 0.5 } = options;

  const url = buildNimUrl(gatewayUrl, 8002, '/biology/arc/evo2/generate');

  const requestBody = {
    sequence: dnaSequence,
    temperature: temperature,
    top_k: 4,
    top_p: 0.95,
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
    throw new Error(`Evo2 service unavailable: ${message}`);
  }

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Evo2 extension failed: ${response.status} - ${errorText}`);
  }

  const data = await response.json();
  return data.sequence || dnaSequence;
}

/**
 * Calculate GC content of a DNA sequence
 */
export function calculateGcContent(dnaSequence: string): number {
  const gc = (dnaSequence.match(/[GC]/gi) || []).length;
  return gc / dnaSequence.length;
}

/**
 * Translate DNA sequence to protein
 */
export function dnaToProtein(dnaSequence: string): string {
  const codonToAa: Record<string, string> = {
    'TTT': 'F', 'TTC': 'F', 'TTA': 'L', 'TTG': 'L',
    'TCT': 'S', 'TCC': 'S', 'TCA': 'S', 'TCG': 'S',
    'TAT': 'Y', 'TAC': 'Y', 'TAA': '*', 'TAG': '*',
    'TGT': 'C', 'TGC': 'C', 'TGA': '*', 'TGG': 'W',
    'CTT': 'L', 'CTC': 'L', 'CTA': 'L', 'CTG': 'L',
    'CCT': 'P', 'CCC': 'P', 'CCA': 'P', 'CCG': 'P',
    'CAT': 'H', 'CAC': 'H', 'CAA': 'Q', 'CAG': 'Q',
    'CGT': 'R', 'CGC': 'R', 'CGA': 'R', 'CGG': 'R',
    'ATT': 'I', 'ATC': 'I', 'ATA': 'I', 'ATG': 'M',
    'ACT': 'T', 'ACC': 'T', 'ACA': 'T', 'ACG': 'T',
    'AAT': 'N', 'AAC': 'N', 'AAA': 'K', 'AAG': 'K',
    'AGT': 'S', 'AGC': 'S', 'AGA': 'R', 'AGG': 'R',
    'GTT': 'V', 'GTC': 'V', 'GTA': 'V', 'GTG': 'V',
    'GCT': 'A', 'GCC': 'A', 'GCA': 'A', 'GCG': 'A',
    'GAT': 'D', 'GAC': 'D', 'GAA': 'E', 'GAG': 'E',
    'GGT': 'G', 'GGC': 'G', 'GGA': 'G', 'GGG': 'G',
  };

  let protein = '';
  const seq = dnaSequence.toUpperCase();

  for (let i = 0; i < seq.length - 2; i += 3) {
    const codon = seq.substring(i, i + 3);
    const aa = codonToAa[codon];
    if (aa === '*') break; // Stop codon
    protein += aa || 'X';
  }

  return protein;
}
