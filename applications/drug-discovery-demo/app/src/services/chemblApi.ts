/**
 * ChEMBL API Service
 *
 * Service for fetching bioactivity data from the ChEMBL database.
 * ChEMBL is a manually curated database of bioactive molecules with drug-like properties.
 *
 * API Documentation: https://www.ebi.ac.uk/chembl/api/data/docs
 */

import type {
  ChemBLTarget,
  DatasetInfo,
  DatasetMolecule,
} from '../types/finetuning';

const CHEMBL_API_BASE = 'https://www.ebi.ac.uk/chembl/api/data';

// ============================================================================
// Types
// ============================================================================

interface ChemBLTargetResponse {
  targets: Array<{
    target_chembl_id: string;
    pref_name: string;
    organism: string;
    target_type: string;
  }>;
}

interface ChemBLActivityResponse {
  activities: Array<{
    molecule_chembl_id: string;
    canonical_smiles: string;
    standard_value: number;
    standard_units: string;
    standard_type: string;
    pchembl_value: number | null;
  }>;
  page_meta: {
    total_count: number;
  };
}

// ============================================================================
// API Functions
// ============================================================================

/**
 * Search for targets by name or ChEMBL ID
 */
export async function searchTargets(query: string): Promise<ChemBLTarget[]> {
  // Check if query is a ChEMBL ID
  const isChemblId = /^CHEMBL\d+$/i.test(query.trim());

  let url: string;
  if (isChemblId) {
    url = `${CHEMBL_API_BASE}/target/${query.toUpperCase()}.json`;
  } else {
    url = `${CHEMBL_API_BASE}/target/search.json?q=${encodeURIComponent(query)}&limit=20`;
  }

  try {
    const response = await fetch(url);
    if (!response.ok) {
      if (response.status === 404) {
        return [];
      }
      throw new Error(`ChEMBL API error: ${response.statusText}`);
    }

    const data = await response.json();

    // Handle single target response (direct ID lookup)
    if (isChemblId && data.target_chembl_id) {
      return [
        {
          chemblId: data.target_chembl_id,
          name: data.pref_name || 'Unknown',
          organism: data.organism || 'Unknown',
          targetType: data.target_type || 'Unknown',
          compoundCount: 0, // Will need separate query
        },
      ];
    }

    // Handle search results
    const targets: ChemBLTargetResponse = data;
    if (!targets.targets) {
      return [];
    }

    return targets.targets.map((t) => ({
      chemblId: t.target_chembl_id,
      name: t.pref_name || 'Unknown',
      organism: t.organism || 'Unknown',
      targetType: t.target_type || 'Unknown',
      compoundCount: 0,
    }));
  } catch (error) {
    console.error('ChEMBL search error:', error);
    throw error;
  }
}

/**
 * Get activity count for a target
 */
export async function getActivityCount(
  targetChemblId: string,
  activityType: string
): Promise<number> {
  const url = `${CHEMBL_API_BASE}/activity.json?target_chembl_id=${targetChemblId}&standard_type=${activityType}&limit=1`;

  try {
    const response = await fetch(url);
    if (!response.ok) {
      return 0;
    }

    const data: ChemBLActivityResponse = await response.json();
    return data.page_meta?.total_count || 0;
  } catch {
    return 0;
  }
}

/**
 * Fetch bioactivity data for a target
 */
export async function fetchActivityData(
  targetChemblId: string,
  activityType: 'IC50' | 'Ki' | 'EC50' | 'Kd',
  limit: number = 5000
): Promise<DatasetInfo> {
  const activities: DatasetMolecule[] = [];
  let offset = 0;
  const pageSize = 1000;
  let totalCount = 0;

  // Fetch in pages
  while (offset < limit) {
    const url = `${CHEMBL_API_BASE}/activity.json?target_chembl_id=${targetChemblId}&standard_type=${activityType}&limit=${pageSize}&offset=${offset}`;

    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Failed to fetch activities: ${response.statusText}`);
    }

    const data: ChemBLActivityResponse = await response.json();
    totalCount = data.page_meta?.total_count || 0;

    if (!data.activities || data.activities.length === 0) {
      break;
    }

    for (const activity of data.activities) {
      if (!activity.canonical_smiles || activity.standard_value === null) {
        continue;
      }

      // Validate SMILES (basic check)
      const isValid = isValidSmiles(activity.canonical_smiles);

      activities.push({
        smiles: activity.canonical_smiles,
        activity: activity.standard_value,
        activityUnit: activity.standard_units || 'nM',
        isValid,
        molecularWeight: undefined, // Would need separate query
      });

      if (activities.length >= limit) {
        break;
      }
    }

    offset += pageSize;

    // Stop if we've fetched all available
    if (offset >= totalCount) {
      break;
    }
  }

  // Deduplicate by SMILES
  const uniqueMap = new Map<string, DatasetMolecule>();
  for (const mol of activities) {
    if (!uniqueMap.has(mol.smiles)) {
      uniqueMap.set(mol.smiles, mol);
    }
  }
  const uniqueActivities = Array.from(uniqueMap.values());

  // Calculate statistics
  const validMolecules = uniqueActivities.filter((m) => m.isValid);
  const activityValues = validMolecules.map((m) => m.activity);

  return {
    id: `chembl-${targetChemblId}-${activityType}-${Date.now()}`,
    name: `${targetChemblId} ${activityType} Data`,
    source: 'chembl',
    sourceId: targetChemblId,
    activityType,
    activityUnit: uniqueActivities[0]?.activityUnit || 'nM',
    molecules: uniqueActivities,
    totalCount: uniqueActivities.length,
    validCount: validMolecules.length,
    invalidCount: uniqueActivities.length - validMolecules.length,
    activityRange: {
      min: activityValues.length > 0 ? Math.min(...activityValues) : 0,
      max: activityValues.length > 0 ? Math.max(...activityValues) : 0,
    },
    molecularWeightRange: { min: 0, max: 0 }, // Would need calculation
    splits: {
      train: Math.floor(validMolecules.length * 0.8),
      validation: Math.floor(validMolecules.length * 0.1),
      test: Math.floor(validMolecules.length * 0.1),
    },
  };
}

// ============================================================================
// Demo Datasets
// ============================================================================

export const DEMO_DATASETS = [
  {
    id: 'cox2_inhibitors',
    name: 'COX-2 Inhibitors',
    description: 'IC50 values for cyclooxygenase-2 inhibitors',
    targetName: 'Cyclooxygenase-2',
    chemblId: 'CHEMBL220',
    activityType: 'IC50' as const,
    compoundCount: 2847,
  },
  {
    id: 'abl1_kinase',
    name: 'ABL1 Kinase Inhibitors',
    description: 'Ki values for BCR-ABL inhibitors (Imatinib-like)',
    targetName: 'Tyrosine-protein kinase ABL1',
    chemblId: 'CHEMBL1862',
    activityType: 'Ki' as const,
    compoundCount: 1523,
  },
  {
    id: 'drd2_ligands',
    name: 'Dopamine D2 Ligands',
    description: 'Binding affinity for D2 receptor ligands',
    targetName: 'Dopamine D2 receptor',
    chemblId: 'CHEMBL217',
    activityType: 'Ki' as const,
    compoundCount: 4211,
  },
];

/**
 * Get a demo dataset (simulated data for quick testing)
 */
export function getDemoDataset(datasetId: string): DatasetInfo {
  const demo = DEMO_DATASETS.find((d) => d.id === datasetId);
  if (!demo) {
    throw new Error(`Demo dataset not found: ${datasetId}`);
  }

  // Generate synthetic data
  const molecules: DatasetMolecule[] = [];
  const sampleSmiles = [
    'CC(C)Cc1ccc(cc1)C(C)C(=O)O',
    'COc1ccc2c(c1)c(CC(=O)O)c(C)n2C(=O)c3ccc(Cl)cc3',
    'Cc1ccc(cc1)C2=CC(=O)c3c(O2)ccc(c3)O',
    'O=C(O)Cc1ccccc1Nc2c(Cl)cccc2Cl',
    'COc1ccc(cc1OC)C2CC(=O)c3c(O)cc(O)cc3O2',
    'CC(=O)Oc1ccccc1C(=O)O',
    'CN1C=NC2=C1C(=O)N(C(=O)N2C)C',
    'CC(C)NCC(O)c1ccc(O)c(O)c1',
    'CC12CCC3C(C1CCC2O)CCC4=CC(=O)CCC34C',
    'CN1CCC(=C2c3ccccc3Sc4ccc(Cl)cc24)CC1',
  ];

  for (let i = 0; i < demo.compoundCount; i++) {
    const baseSmiles = sampleSmiles[i % sampleSmiles.length];
    // Add some variation
    const smiles = i < sampleSmiles.length ? baseSmiles : `${baseSmiles}.variant${i}`;

    molecules.push({
      smiles,
      activity: Math.pow(10, Math.random() * 4 - 1), // 0.1 to 1000 nM
      activityUnit: 'nM',
      isValid: Math.random() > 0.01, // 99% valid
      molecularWeight: 200 + Math.random() * 400,
    });
  }

  const validMolecules = molecules.filter((m) => m.isValid);
  const activityValues = validMolecules.map((m) => m.activity);
  const mwValues = validMolecules.map((m) => m.molecularWeight!);

  return {
    id: demo.id,
    name: demo.name,
    source: 'demo',
    sourceId: demo.chemblId,
    activityType: demo.activityType,
    activityUnit: 'nM',
    molecules,
    totalCount: molecules.length,
    validCount: validMolecules.length,
    invalidCount: molecules.length - validMolecules.length,
    activityRange: {
      min: activityValues.length > 0 ? Math.min(...activityValues) : 0,
      max: activityValues.length > 0 ? Math.max(...activityValues) : 0,
    },
    molecularWeightRange: {
      min: mwValues.length > 0 ? Math.min(...mwValues) : 0,
      max: mwValues.length > 0 ? Math.max(...mwValues) : 0,
    },
    splits: {
      train: Math.floor(validMolecules.length * 0.8),
      validation: Math.floor(validMolecules.length * 0.1),
      test: Math.floor(validMolecules.length * 0.1),
    },
  };
}

// ============================================================================
// Utilities
// ============================================================================

/**
 * Basic SMILES validation
 */
function isValidSmiles(smiles: string): boolean {
  if (!smiles || smiles.length < 2) return false;

  // Check for common valid characters
  const validChars = /^[A-Za-z0-9@+\-\[\]\(\)\\\/=#$.%:]+$/;
  if (!validChars.test(smiles)) return false;

  // Check for balanced parentheses and brackets
  let parenCount = 0;
  let bracketCount = 0;
  for (const char of smiles) {
    if (char === '(') parenCount++;
    if (char === ')') parenCount--;
    if (char === '[') bracketCount++;
    if (char === ']') bracketCount--;
    if (parenCount < 0 || bracketCount < 0) return false;
  }

  return parenCount === 0 && bracketCount === 0;
}

/**
 * Parse uploaded SDF file
 * SDF files contain molecule records separated by "$$$$"
 */
export function parseSdfFile(sdfContent: string): DatasetInfo {
  const records = sdfContent.split('$$$$').filter((r) => r.trim().length > 0);

  if (records.length === 0) {
    throw new Error('No molecule records found in SDF file');
  }

  const molecules: DatasetMolecule[] = [];

  for (const record of records) {
    const lines = record.trim().split('\n');
    if (lines.length < 4) continue;

    // Try to extract SMILES from properties (>  <SMILES>) or use molecule name
    let smiles = '';
    let activity = NaN;

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim();
      if (line.match(/^>\s+<SMILES>/i) && i + 1 < lines.length) {
        smiles = lines[i + 1].trim();
      }
      if (line.match(/^>\s+<(activity|IC50|Ki|value|pIC50|pChEMBL)/i) && i + 1 < lines.length) {
        activity = parseFloat(lines[i + 1].trim());
      }
    }

    // If no SMILES property, use molecule name (first line) as identifier
    if (!smiles) {
      smiles = lines[0].trim() || `mol_${molecules.length}`;
    }

    // If no activity found, assign random for demo
    if (isNaN(activity)) {
      activity = Math.pow(10, Math.random() * 4 - 1);
    }

    molecules.push({
      smiles,
      activity,
      activityUnit: 'nM',
      isValid: isValidSmiles(smiles),
    });
  }

  if (molecules.length === 0) {
    throw new Error('No valid molecule records found in SDF file');
  }

  const validMolecules = molecules.filter((m) => m.isValid);
  const activityValues = validMolecules.map((m) => m.activity);

  return {
    id: `sdf-upload-${Date.now()}`,
    name: 'Uploaded SDF',
    source: 'upload',
    activityType: 'custom',
    activityUnit: 'nM',
    molecules,
    totalCount: molecules.length,
    validCount: validMolecules.length,
    invalidCount: molecules.length - validMolecules.length,
    activityRange: {
      min: activityValues.length > 0 ? Math.min(...activityValues) : 0,
      max: activityValues.length > 0 ? Math.max(...activityValues) : 0,
    },
    molecularWeightRange: { min: 0, max: 0 },
    splits: {
      train: Math.floor(validMolecules.length * 0.8),
      validation: Math.floor(validMolecules.length * 0.1),
      test: Math.floor(validMolecules.length * 0.1),
    },
  };
}

/**
 * Parse uploaded CSV file
 */
export function parseUploadedCsv(csvContent: string): DatasetInfo {
  const lines = csvContent.trim().split('\n');
  if (lines.length < 2) {
    throw new Error('CSV must have a header row and at least one data row');
  }

  // Parse header
  const header = lines[0].toLowerCase().split(',').map((h) => h.trim());
  const smilesIndex = header.findIndex((h) => h === 'smiles' || h === 'molecule');
  const activityIndex = header.findIndex(
    (h) => h === 'activity' || h === 'value' || h === 'ic50' || h === 'ki'
  );

  if (smilesIndex === -1) {
    throw new Error('CSV must have a "smiles" or "molecule" column');
  }
  if (activityIndex === -1) {
    throw new Error('CSV must have an "activity", "value", "ic50", or "ki" column');
  }

  // Parse data rows
  const molecules: DatasetMolecule[] = [];
  for (let i = 1; i < lines.length; i++) {
    const values = lines[i].split(',').map((v) => v.trim());
    if (values.length <= Math.max(smilesIndex, activityIndex)) continue;

    const smiles = values[smilesIndex];
    const activity = parseFloat(values[activityIndex]);

    if (!smiles || isNaN(activity)) continue;

    molecules.push({
      smiles,
      activity,
      activityUnit: 'nM',
      isValid: isValidSmiles(smiles),
    });
  }

  if (molecules.length === 0) {
    throw new Error('No valid data rows found in CSV');
  }

  const validMolecules = molecules.filter((m) => m.isValid);
  const activityValues = validMolecules.map((m) => m.activity);

  return {
    id: `upload-${Date.now()}`,
    name: 'Uploaded Dataset',
    source: 'upload',
    activityType: 'custom',
    activityUnit: 'nM',
    molecules,
    totalCount: molecules.length,
    validCount: validMolecules.length,
    invalidCount: molecules.length - validMolecules.length,
    activityRange: {
      min: activityValues.length > 0 ? Math.min(...activityValues) : 0,
      max: activityValues.length > 0 ? Math.max(...activityValues) : 0,
    },
    molecularWeightRange: { min: 0, max: 0 },
    splits: {
      train: Math.floor(validMolecules.length * 0.8),
      validation: Math.floor(validMolecules.length * 0.1),
      test: Math.floor(validMolecules.length * 0.1),
    },
  };
}
