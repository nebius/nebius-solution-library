// Docking API service (DiffDock)

import { buildNimUrl } from './nimApi';

export interface DockingPose {
  ligand_positions: string; // SDF format
  confidence: number; // Normalized confidence (0-1 scale via exp(raw_score))
  position_confidence: number; // Raw DiffDock score (log scale, closer to 0 is better)
  affinity?: number;
}

export interface DockingResult {
  ligandSmiles: string;
  poses: DockingPose[];
  bestConfidence: number;
  bestAffinity?: number;
  elapsedTime: number;
}

export interface DiffDockRequest {
  protein: string; // PDB format
  ligand: string; // SMILES (when ligand_file_type is "txt")
  ligand_file_type: 'mol2' | 'sdf' | 'txt';
  num_poses?: number;
  time_divisions?: number;
  steps?: number;
  save_trajectory?: boolean;
  is_staged?: boolean;
}

/**
 * Build default DiffDock request
 *
 * Note: DiffDock is a diffusion model with inherent stochasticity.
 * Higher num_poses gives more consistent "best" results by sampling more.
 * The API doesn't support a seed parameter for reproducibility.
 *
 * 2024 research shows 30 poses is optimal for accuracy/compute tradeoff.
 * See: https://onlinescientificresearch.com/articles/determining-the-optimal-tradeoff-between-compute-and-accuracy-for-diffusion-models-in-molecular-docking.pdf
 */
export function buildDiffDockRequest(
  proteinPdb: string,
  ligandSmiles: string,
  numPoses: number = 30
): DiffDockRequest {
  return {
    protein: proteinPdb,
    ligand: ligandSmiles,
    ligand_file_type: 'txt', // Use 'txt' for SMILES input
    num_poses: numPoses,
    time_divisions: 20,
    steps: 18,
    save_trajectory: false,
    is_staged: false,
  };
}

/**
 * Convert CIF/mmCIF to PDB format (simplified conversion)
 * In production, you'd use a proper conversion library
 * DiffDock typically requires PDB format
 */
export function convertToPdb(structure: string, format: 'pdb' | 'cif' | 'mmcif'): string {
  if (format === 'pdb') {
    return structure;
  }

  // For CIF/mmCIF, we need to extract atomic coordinates
  // This is a simplified extraction - in production use proper libraries
  const lines = structure.split('\n');
  const pdbLines: string[] = [];
  let atomSerial = 1;

  // Try to find _atom_site section in CIF
  let inAtomSite = false;
  const atomSiteFields: string[] = [];
  let fieldIndices: Record<string, number> = {};

  for (const line of lines) {
    const trimmed = line.trim();

    // Detect _atom_site header fields
    if (trimmed.startsWith('_atom_site.')) {
      const fieldName = trimmed.replace('_atom_site.', '');
      atomSiteFields.push(fieldName);
      fieldIndices[fieldName] = atomSiteFields.length - 1;
      continue;
    }

    // Skip loop_ and other directives
    if (trimmed.startsWith('loop_') || trimmed.startsWith('#') || trimmed.startsWith('data_')) {
      continue;
    }

    // If we have atom_site fields defined and this line starts with ATOM or HETATM
    if (atomSiteFields.length > 0 && (trimmed.startsWith('ATOM') || trimmed.startsWith('HETATM'))) {
      inAtomSite = true;
    }

    // Parse atom lines if we're in atom_site section
    if (inAtomSite && atomSiteFields.length > 0) {
      const fields = trimmed.split(/\s+/);
      if (fields.length >= atomSiteFields.length && (fields[0] === 'ATOM' || fields[0] === 'HETATM')) {
        try {
          const recordType = fields[fieldIndices['group_PDB']] || 'ATOM';
          const atomName = fields[fieldIndices['label_atom_id']] || fields[fieldIndices['auth_atom_id']] || 'X';
          const resName = fields[fieldIndices['label_comp_id']] || fields[fieldIndices['auth_comp_id']] || 'UNK';
          const chainId = fields[fieldIndices['label_asym_id']] || fields[fieldIndices['auth_asym_id']] || 'A';
          const resSeq = fields[fieldIndices['label_seq_id']] || fields[fieldIndices['auth_seq_id']] || '1';
          const x = parseFloat(fields[fieldIndices['Cartn_x']] || '0');
          const y = parseFloat(fields[fieldIndices['Cartn_y']] || '0');
          const z = parseFloat(fields[fieldIndices['Cartn_z']] || '0');
          const element = fields[fieldIndices['type_symbol']] || atomName.charAt(0);
          const bFactor = parseFloat(fields[fieldIndices['B_iso_or_equiv']] || '0');

          // Format PDB ATOM line
          const pdbLine = formatPdbAtomLine(
            recordType === 'HETATM' ? 'HETATM' : 'ATOM',
            atomSerial++,
            atomName,
            resName,
            chainId,
            parseInt(resSeq),
            x,
            y,
            z,
            1.0,
            bFactor,
            element
          );
          pdbLines.push(pdbLine);
        } catch {
          // Skip malformed lines
        }
      }
    }
  }

  // If we couldn't parse CIF format, try simple ATOM line extraction
  if (pdbLines.length === 0) {
    for (const line of lines) {
      if (line.startsWith('ATOM') || line.startsWith('HETATM')) {
        pdbLines.push(line);
      }
    }
  }

  // If we couldn't extract any atoms, log a warning
  if (pdbLines.length === 0) {
    console.warn('CIF/mmCIF to PDB conversion: No atoms extracted from structure. Check format.');
  }

  pdbLines.push('END');
  return pdbLines.join('\n');
}

/**
 * Format a PDB ATOM line
 */
function formatPdbAtomLine(
  recordType: 'ATOM' | 'HETATM',
  serial: number,
  atomName: string,
  resName: string,
  chainId: string,
  resSeq: number,
  x: number,
  y: number,
  z: number,
  occupancy: number,
  bFactor: number,
  element: string
): string {
  // PDB format is fixed-width columns
  const record = recordType.padEnd(6);
  const serialStr = serial.toString().padStart(5);
  const atomNameStr = atomName.length < 4 ? ` ${atomName}`.padEnd(4) : atomName.substring(0, 4);
  const resNameStr = resName.padEnd(3);
  const chainIdStr = chainId.charAt(0);
  const resSeqStr = resSeq.toString().padStart(4);
  const xStr = x.toFixed(3).padStart(8);
  const yStr = y.toFixed(3).padStart(8);
  const zStr = z.toFixed(3).padStart(8);
  const occStr = occupancy.toFixed(2).padStart(6);
  const bStr = bFactor.toFixed(2).padStart(6);
  const elemStr = element.padStart(2);

  return `${record}${serialStr} ${atomNameStr} ${resNameStr} ${chainIdStr}${resSeqStr}    ${xStr}${yStr}${zStr}${occStr}${bStr}          ${elemStr}`;
}

/**
 * Dock a single ligand to a protein using DiffDock
 */
export async function dockLigand(
  gatewayUrl: string,
  proteinStructure: string,
  proteinFormat: 'pdb' | 'cif' | 'mmcif',
  ligandSmiles: string,
  numPoses: number = 5
): Promise<DockingResult> {
  const startTime = Date.now();
  // Correct endpoint path for DiffDock NIM
  const url = buildNimUrl(gatewayUrl, 8007, '/molecular-docking/diffdock/generate');

  // Convert to PDB if necessary
  const proteinPdb = convertToPdb(proteinStructure, proteinFormat);

  // Verify we have a valid PDB structure
  const atomCount = (proteinPdb.match(/^ATOM\s/gm) || []).length;
  if (atomCount === 0) {
    throw new Error(`CIF to PDB conversion failed: No atoms extracted from ${proteinFormat.toUpperCase()} structure`);
  }
  console.log(`DiffDock: Docking ${ligandSmiles.substring(0, 30)}... to structure with ${atomCount} atoms`);

  const requestBody = buildDiffDockRequest(proteinPdb, ligandSmiles, numPoses);

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
    throw new Error(`DiffDock service unavailable: ${message}`);
  }

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`DiffDock docking failed: ${response.status} - ${errorText}`);
  }

  const data = await response.json();
  const elapsedTime = Date.now() - startTime;

  // Check for failed status
  if (data.status === 'failed') {
    throw new Error(`DiffDock failed: ${data.details || 'Unknown error'}`);
  }

  // Parse DiffDock response
  // Response format: { ligand_positions: [...], position_confidence: [...], status: "success"|"failed", details: "..." }
  const poses: DockingPose[] = [];

  if (Array.isArray(data.ligand_positions)) {
    for (let i = 0; i < data.ligand_positions.length; i++) {
      // Skip empty positions
      if (!data.ligand_positions[i]) continue;

      const posConfidence = data.position_confidence?.[i];
      // position_confidence can be null for failed poses
      if (posConfidence === null || posConfidence === undefined) continue;

      // DiffDock returns confidence on log scale (negative values, closer to 0 is better)
      // Convert to 0-1 scale using exp() for display purposes
      // Clamp to [0, 1] since positive raw scores (very good poses) would give exp() > 1
      const normalizedConfidence = Math.min(1, Math.exp(posConfidence));

      poses.push({
        ligand_positions: data.ligand_positions[i],
        confidence: normalizedConfidence,
        position_confidence: posConfidence, // Keep raw score for reference
      });
    }
  }

  // Sort by confidence descending
  poses.sort((a, b) => b.confidence - a.confidence);

  const bestConfidence = poses.length > 0 ? poses[0].confidence : 0;

  return {
    ligandSmiles,
    poses,
    bestConfidence,
    elapsedTime,
  };
}

/**
 * Dock multiple ligands in parallel
 * @param concurrency - Number of parallel API calls (default: 3)
 */
export async function dockMultipleLigands(
  gatewayUrl: string,
  proteinStructure: string,
  proteinFormat: 'pdb' | 'cif' | 'mmcif',
  ligandSmiles: string[],
  numPosesPerLigand: number = 3,
  onProgress?: (completed: number, total: number, result?: DockingResult) => void,
  concurrency: number = 3
): Promise<DockingResult[]> {
  const results: DockingResult[] = [];
  const total = ligandSmiles.length;

  // Process ligands with configurable concurrency (multiple instances behind load balancer)
  const concurrencyLimit = Math.max(1, Math.min(concurrency, 10)); // Clamp between 1-10
  let completed = 0;

  for (let i = 0; i < ligandSmiles.length; i += concurrencyLimit) {
    const batch = ligandSmiles.slice(i, i + concurrencyLimit);
    const batchPromises = batch.map(async (smiles) => {
      try {
        const result = await dockLigand(
          gatewayUrl,
          proteinStructure,
          proteinFormat,
          smiles,
          numPosesPerLigand
        );
        completed++;
        onProgress?.(completed, total, result);
        return result;
      } catch (error) {
        completed++;
        const errorResult: DockingResult = {
          ligandSmiles: smiles,
          poses: [],
          bestConfidence: 0,
          elapsedTime: 0,
        };
        onProgress?.(completed, total, errorResult);
        return errorResult;
      }
    });

    const batchResults = await Promise.all(batchPromises);
    results.push(...batchResults);
  }

  return results;
}

/**
 * Get the best docking results sorted by confidence
 */
export function getBestDockingResults(
  results: DockingResult[],
  topN: number = 10
): DockingResult[] {
  return [...results]
    .filter(r => r.poses.length > 0)
    .sort((a, b) => b.bestConfidence - a.bestConfidence)
    .slice(0, topN);
}

/**
 * Format confidence score for display
 */
export function formatConfidence(confidence: number): string {
  // DiffDock confidence is typically in [0, 1]
  return `${(confidence * 100).toFixed(1)}%`;
}

/**
 * Get confidence level category
 */
export function getConfidenceLevel(confidence: number): 'high' | 'medium' | 'low' {
  if (confidence >= 0.7) return 'high';
  if (confidence >= 0.4) return 'medium';
  return 'low';
}
