// MSA (Multiple Sequence Alignment) Search API service

import { buildNimUrl } from './nimApi';

export interface MsaSearchResult {
  alignment: string; // A3M format alignment
  format: 'a3m';
  numSequences: number;
  queryLength: number;
}

export interface MsaSearchOptions {
  databases?: string[];
  outputFormats?: string[];
}

/**
 * Search for homologous sequences using MSA Search (ColabFold)
 * Returns a multiple sequence alignment that can be used with OpenFold2/3
 */
export async function searchMsa(
  gatewayUrl: string,
  sequence: string,
  options: MsaSearchOptions = {}
): Promise<MsaSearchResult> {
  const { databases = ['all'], outputFormats = ['a3m'] } = options;

  const url = buildNimUrl(gatewayUrl, 8003, '/biology/colabfold/msa-search/predict');

  const requestBody = {
    sequence: sequence,
    databases: databases,
    output_alignment_formats: outputFormats,
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
    throw new Error(`MSA Search service unavailable: ${message}. The service may be down or restarting.`);
  }

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`MSA Search failed: ${response.status} - ${errorText}`);
  }

  const data = await response.json();

  // Response structure: { alignments: { database_name: { format: { alignment: "..." } } } }
  // Find the first A3M alignment in the response
  let alignment = '';

  if (data.alignments) {
    // Iterate through databases to find an A3M alignment
    for (const dbName of Object.keys(data.alignments)) {
      const dbData = data.alignments[dbName];
      if (dbData?.a3m?.alignment) {
        alignment = dbData.a3m.alignment;
        break;
      }
    }
  }

  // Fallback for simpler response structures
  if (!alignment) {
    alignment = data.a3m || data.alignment || '';
  }

  if (!alignment) {
    throw new Error('No MSA alignment returned from search');
  }

  // Count sequences in A3M (each sequence starts with >)
  const numSequences = (alignment.match(/^>/gm) || []).length;

  return {
    alignment,
    format: 'a3m',
    numSequences,
    queryLength: sequence.length,
  };
}

/**
 * Convert A3M alignment to CSV format for OpenFold3
 *
 * A3M format rules:
 * - First sequence is the query (no lowercase, no gaps in original)
 * - Subsequent sequences may have:
 *   - Lowercase letters = insertions relative to query (should be removed)
 *   - '-' = deletions/gaps (should be kept)
 *
 * CSV format rules for OpenFold3:
 * - All keys should be -1
 * - First sequence must exactly match input protein sequence
 * - Gaps represented as '-'
 */
export function a3mToCsv(a3m: string, querySequence: string): string {
  const lines = a3m.trim().split('\n');
  const rows: string[] = ['key,sequence'];

  // First row is always the query sequence (must match exactly)
  rows.push(`-1,${querySequence}`);

  let currentSeq = '';
  let isFirstSequence = true;
  let inSequence = false;

  for (const line of lines) {
    if (line.startsWith('>')) {
      // Save previous sequence if exists (skip the first/query sequence)
      if (inSequence && currentSeq && !isFirstSequence) {
        // Remove lowercase letters (insertions) from hit sequences
        const cleanedSeq = currentSeq.replace(/[a-z]/g, '');
        rows.push(`-1,${cleanedSeq}`);
      }
      currentSeq = '';
      inSequence = true;
      if (isFirstSequence) {
        isFirstSequence = false;
      }
    } else if (inSequence) {
      currentSeq += line.trim();
    }
  }

  // Save last sequence
  if (currentSeq && !isFirstSequence) {
    const cleanedSeq = currentSeq.replace(/[a-z]/g, '');
    rows.push(`-1,${cleanedSeq}`);
  }

  return rows.join('\n');
}

/**
 * Build OpenFold3 request with real MSA data
 *
 * WARNING: Testing shows OpenFold3 performs WORSE with real MSA (~12%) than
 * with single-sequence MSA (~33%). This is a known limitation of OpenFold3
 * per NVIDIA docs. Use buildOpenFold3Request() with single sequence instead.
 *
 * @deprecated Use single-sequence MSA for OpenFold3. MSA only helps OpenFold2.
 * @param numCopies - Number of chain copies for homo-oligomers (default: 1)
 */
export function buildOpenFold3RequestWithMsa(
  sequence: string,
  msaA3m: string,
  numCopies = 1
): Record<string, unknown> {
  // Generate chain IDs: A, B, C, ... based on number of copies
  const chainIds = Array.from({ length: numCopies }, (_, i) => String.fromCharCode(65 + i));

  // For homodimers, add multiple molecules with different IDs
  const molecules = chainIds.map((id) => ({
    type: 'protein',
    id: id,
    sequence: sequence,
    msa: {
      main: {
        a3m: {
          alignment: msaA3m,
          format: 'a3m',
        },
      },
    },
  }));

  // Use a3m format with 'main' db (performs slightly better than csv with main_db)
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
 * Build OpenFold2 request with real MSA data
 * Note: OpenFold2 uses 'alignments' not 'msa'
 */
export function buildOpenFold2RequestWithMsa(
  sequence: string,
  msaA3m: string
): Record<string, unknown> {
  return {
    sequence: sequence,
    alignments: {
      uniref90: {
        a3m: {
          alignment: msaA3m,
          format: 'a3m',
        },
      },
    },
    selected_models: [1, 2, 3, 4, 5],
    output_format: 'cif',
  };
}
