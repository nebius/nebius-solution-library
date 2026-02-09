/**
 * Drug-likeness validation using Lipinski's Rule of Five
 * and related pharmaceutical filters
 */

// Atomic weights for common elements
const ATOMIC_WEIGHTS: Record<string, number> = {
  C: 12.011,
  N: 14.007,
  O: 15.999,
  S: 32.065,
  F: 18.998,
  Cl: 35.453,
  Br: 79.904,
  I: 126.904,
  P: 30.974,
  Si: 28.086,
  H: 1.008,
  B: 10.811,
};

export interface LipinskiResult {
  molecularWeight: number;
  hBondDonors: number;
  hBondAcceptors: number;
  logP: number; // Estimated
  rotatableBonds: number;
  violations: number;
  passes: boolean;
  details: {
    mwPass: boolean;
    hbdPass: boolean;
    hbaPass: boolean;
    logPPass: boolean;
  };
}

export interface DrugLikenessResult {
  lipinski: LipinskiResult;
  drugLikenessScore: number; // 0-1 score
  alerts: string[];
  properties: {
    tpsa: number; // Topological Polar Surface Area estimate
    numRings: number;
    numAromaticRings: number;
    numHeavyAtoms: number;
  };
}

/**
 * Parse SMILES and extract basic atom counts
 */
function parseSmilesAtoms(smiles: string): { atoms: Record<string, number>; bonds: number } {
  const atoms: Record<string, number> = { C: 0, N: 0, O: 0, S: 0, F: 0, Cl: 0, Br: 0, I: 0, P: 0, Si: 0, B: 0 };
  let bonds = 0;

  // Remove stereochemistry and branch indicators for counting
  const simplified = smiles.replace(/\[.*?\]/g, (match) => {
    // Parse bracketed atoms like [NH2], [O-], [nH], etc.
    const atomMatch = match.match(/\[([A-Z][a-z]?)/);
    if (atomMatch) {
      const atom = atomMatch[1];
      if (atom in atoms) {
        atoms[atom]++;
      }
    }
    return '';
  });

  // Count atoms in the remaining string
  let i = 0;
  while (i < simplified.length) {
    const char = simplified[i];

    // Two-letter atoms
    if (i + 1 < simplified.length) {
      const twoChar = char + simplified[i + 1];
      if (twoChar === 'Cl' || twoChar === 'Br' || twoChar === 'Si') {
        atoms[twoChar]++;
        i += 2;
        continue;
      }
    }

    // Single letter atoms
    if (char === 'C' && simplified[i + 1] !== 'l') {
      atoms.C++;
    } else if (char === 'N') {
      atoms.N++;
    } else if (char === 'O') {
      atoms.O++;
    } else if (char === 'S' && simplified[i + 1] !== 'i') {
      atoms.S++;
    } else if (char === 'F') {
      atoms.F++;
    } else if (char === 'I') {
      atoms.I++;
    } else if (char === 'P') {
      atoms.P++;
    } else if (char === 'B' && simplified[i + 1] !== 'r') {
      atoms.B++;
    }

    // Count bonds
    if (char === '-' || char === '=') {
      bonds++;
    }

    i++;
  }

  return { atoms, bonds };
}

/**
 * Estimate molecular weight from SMILES
 */
function estimateMolecularWeight(smiles: string): number {
  const { atoms } = parseSmilesAtoms(smiles);

  let weight = 0;
  for (const [atom, count] of Object.entries(atoms)) {
    weight += (ATOMIC_WEIGHTS[atom] || 0) * count;
  }

  // Add estimated hydrogens (very rough estimate)
  // Based on typical valences
  const estimatedH =
    Math.max(0, atoms.C * 2 - atoms.N - atoms.O) + // Rough hydrocarbon estimate
    atoms.N * 1 + // NH groups
    atoms.O * 0.5; // OH groups
  weight += estimatedH * ATOMIC_WEIGHTS.H;

  return weight;
}

/**
 * Count hydrogen bond donors (NH and OH groups)
 */
function countHBondDonors(smiles: string): number {
  let count = 0;

  // Count explicit NH and OH patterns
  const nhMatches = smiles.match(/\[N[^-\]]*H\d?\]/gi) || [];
  const ohMatches = smiles.match(/\[O[^-\]]*H\]/gi) || [];

  count += nhMatches.length;
  count += ohMatches.length;

  // Count implicit NH (lowercase n is aromatic N, often has H)
  const implicitNH = smiles.match(/n(?![A-Z])/g) || [];
  count += implicitNH.length * 0.5; // Rough estimate

  // Count hydroxyl groups (O not double-bonded or in ether)
  const implicitOH = (smiles.match(/O(?!=)/g) || []).length;
  count += implicitOH * 0.3; // Very rough estimate

  return Math.round(count);
}

/**
 * Count hydrogen bond acceptors (N and O atoms)
 */
function countHBondAcceptors(smiles: string): number {
  const { atoms } = parseSmilesAtoms(smiles);
  return atoms.N + atoms.O;
}

/**
 * Estimate LogP (octanol-water partition coefficient)
 * Using a very simplified atom-based method
 */
function estimateLogP(smiles: string): number {
  const { atoms } = parseSmilesAtoms(smiles);

  // Very rough atom contribution method
  // Based on simplified Wildman-Crippen
  let logP = 0;
  logP += atoms.C * 0.29; // Carbons are lipophilic
  logP += atoms.N * -0.67; // Nitrogens are polar
  logP += atoms.O * -0.47; // Oxygens are polar
  logP += atoms.S * 0.37;
  logP += atoms.F * 0.22;
  logP += atoms.Cl * 0.71;
  logP += atoms.Br * 0.86;
  logP += atoms.I * 1.14;

  // Adjust for aromatic rings (lowercase letters in SMILES)
  const aromaticCount = (smiles.match(/[cnos]/g) || []).length;
  logP += aromaticCount * 0.1;

  return Math.round(logP * 100) / 100;
}

/**
 * Count rotatable bonds (rough estimate)
 */
function countRotatableBonds(smiles: string): number {
  // Count single bonds between non-terminal heavy atoms
  // This is a rough estimate based on SMILES patterns
  const singleBonds = (smiles.match(/[A-Z][a-z]?-[A-Z][a-z]?/g) || []).length;
  const implicitSingleBonds = smiles.length / 5; // Rough heuristic

  return Math.round(Math.max(singleBonds, implicitSingleBonds) * 0.6);
}

/**
 * Count rings in molecule
 */
function countRings(smiles: string): number {
  // Rings are indicated by numbers in SMILES
  const ringNumbers = new Set(smiles.match(/\d/g) || []);
  return ringNumbers.size;
}

/**
 * Count aromatic rings
 */
function countAromaticRings(smiles: string): number {
  // Aromatic atoms are lowercase in SMILES
  const aromaticAtoms = (smiles.match(/[cnos]/g) || []).length;
  // Rough estimate: 6 aromatic atoms per ring on average
  return Math.round(aromaticAtoms / 5);
}

/**
 * Estimate Topological Polar Surface Area
 */
function estimateTPSA(smiles: string): number {
  const { atoms } = parseSmilesAtoms(smiles);
  const hbd = countHBondDonors(smiles);

  // Simplified TPSA calculation
  // Based on fragment contributions
  const nContrib = atoms.N * 23.8; // N with H ~ 26, N without ~ 12
  const oContrib = atoms.O * 18.5; // O with H ~ 20, O= ~ 17
  const sContrib = atoms.S * 5.4;

  // Adjust for H-bond donors
  const hContrib = hbd * 5;

  return Math.round((nContrib + oContrib + sContrib + hContrib) * 10) / 10;
}

/**
 * Check for structural alerts (PAINS, toxicophores, etc.)
 */
function checkStructuralAlerts(smiles: string): string[] {
  const alerts: string[] = [];

  // Reactive functional groups
  if (/N=N=N/i.test(smiles)) alerts.push('Azide group');
  if (/\[N\+\]/.test(smiles) && /O-/.test(smiles)) alerts.push('Nitro group');
  if (/C#N/.test(smiles)) alerts.push('Nitrile group');
  if (/S=O/.test(smiles)) alerts.push('Sulfoxide/sulfone');
  if (/C\(=O\)O[A-Z]/.test(smiles)) alerts.push('Ester (may hydrolyze)');
  if (/C=C[A-Z]O/.test(smiles)) alerts.push('Michael acceptor');
  if (/C1=CC=C\(C=C1\)O/.test(smiles) && /O/.test(smiles)) alerts.push('Phenol');

  // Common PAINS patterns (simplified)
  if (/c1ccc2[nH]c3ccccc3nc2c1/i.test(smiles)) alerts.push('Quinone-like');
  if (/\[N\+\].*\[N\+\]/.test(smiles)) alerts.push('Multiple positive charges');

  return alerts;
}

/**
 * Calculate Lipinski's Rule of Five compliance
 */
export function calculateLipinski(smiles: string): LipinskiResult {
  const mw = estimateMolecularWeight(smiles);
  const hbd = countHBondDonors(smiles);
  const hba = countHBondAcceptors(smiles);
  const logP = estimateLogP(smiles);
  const rotBonds = countRotatableBonds(smiles);

  const mwPass = mw <= 500;
  const hbdPass = hbd <= 5;
  const hbaPass = hba <= 10;
  const logPPass = logP <= 5;

  const violations = [!mwPass, !hbdPass, !hbaPass, !logPPass].filter(Boolean).length;

  return {
    molecularWeight: Math.round(mw * 10) / 10,
    hBondDonors: hbd,
    hBondAcceptors: hba,
    logP,
    rotatableBonds: rotBonds,
    violations,
    passes: violations <= 1, // Allow 1 violation (Lipinski's guideline)
    details: {
      mwPass,
      hbdPass,
      hbaPass,
      logPPass,
    },
  };
}

/**
 * Calculate comprehensive drug-likeness score and properties
 */
export function calculateDrugLikeness(smiles: string): DrugLikenessResult {
  const lipinski = calculateLipinski(smiles);
  const alerts = checkStructuralAlerts(smiles);
  const { atoms } = parseSmilesAtoms(smiles);

  // Calculate additional properties
  const tpsa = estimateTPSA(smiles);
  const numRings = countRings(smiles);
  const numAromaticRings = countAromaticRings(smiles);
  const numHeavyAtoms = Object.values(atoms).reduce((a, b) => a + b, 0);

  // Calculate drug-likeness score (0-1)
  let score = 1.0;

  // Penalize Lipinski violations
  score -= lipinski.violations * 0.15;

  // Penalize extreme values
  if (lipinski.molecularWeight > 600) score -= 0.1;
  if (lipinski.molecularWeight < 150) score -= 0.1;
  if (lipinski.logP > 6) score -= 0.1;
  if (lipinski.logP < -2) score -= 0.05;
  if (tpsa > 140) score -= 0.1; // Poor oral absorption
  if (lipinski.rotatableBonds > 10) score -= 0.1;

  // Penalize structural alerts
  score -= alerts.length * 0.1;

  // Bonus for optimal range
  if (lipinski.molecularWeight >= 250 && lipinski.molecularWeight <= 450) score += 0.05;
  if (lipinski.logP >= 1 && lipinski.logP <= 3) score += 0.05;

  // Clamp to 0-1
  score = Math.max(0, Math.min(1, score));

  return {
    lipinski,
    drugLikenessScore: Math.round(score * 100) / 100,
    alerts,
    properties: {
      tpsa,
      numRings,
      numAromaticRings,
      numHeavyAtoms,
    },
  };
}

/**
 * Get a simple drug-likeness badge/label
 */
export function getDrugLikenessLabel(score: number): { label: string; color: string } {
  if (score >= 0.8) return { label: 'Excellent', color: 'var(--color-success)' };
  if (score >= 0.6) return { label: 'Good', color: 'var(--color-lime)' };
  if (score >= 0.4) return { label: 'Moderate', color: 'var(--color-warning)' };
  return { label: 'Poor', color: 'var(--color-error)' };
}

/**
 * Format Lipinski result as a summary string
 */
export function formatLipinskiSummary(result: LipinskiResult): string {
  const status = result.passes ? 'PASS' : 'FAIL';
  return `Lipinski ${status} (${result.violations} violation${result.violations !== 1 ? 's' : ''})`;
}
