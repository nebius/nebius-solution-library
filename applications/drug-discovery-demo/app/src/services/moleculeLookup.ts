// Molecule name lookup service using PubChem

export interface MoleculeInfo {
  smiles: string;
  name: string | null;
  iupacName: string | null;
  cid: number | null;
  isKnownDrug: boolean;
}

/**
 * Look up molecule information from PubChem by SMILES
 * Uses the PubChem PUG REST API
 */
export async function lookupMoleculeBySmiles(smiles: string): Promise<MoleculeInfo> {
  const result: MoleculeInfo = {
    smiles,
    name: null,
    iupacName: null,
    cid: null,
    isKnownDrug: false,
  };

  try {
    // URL-encode the SMILES
    const encodedSmiles = encodeURIComponent(smiles);

    // First, get the CID from SMILES
    const cidResponse = await fetch(
      `https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/smiles/${encodedSmiles}/cids/JSON`,
      { signal: AbortSignal.timeout(5000) }
    );

    if (!cidResponse.ok) {
      return result;
    }

    const cidData = await cidResponse.json();
    const cid = cidData?.IdentifierList?.CID?.[0];

    if (!cid) {
      return result;
    }

    result.cid = cid;

    // Get properties including Title (common name) and IUPACName
    const propResponse = await fetch(
      `https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/${cid}/property/Title,IUPACName/JSON`,
      { signal: AbortSignal.timeout(5000) }
    );

    if (propResponse.ok) {
      const propData = await propResponse.json();
      const props = propData?.PropertyTable?.Properties?.[0];

      if (props) {
        result.name = props.Title || null;
        result.iupacName = props.IUPACName || null;

        // Check if it's a known drug (simple heuristic: name is short and doesn't look like IUPAC)
        if (result.name && result.name.length < 30 && !/^\d|^\(/.test(result.name)) {
          result.isKnownDrug = true;
        }
      }
    }

    return result;
  } catch (error) {
    // Silently fail - molecule lookup is optional
    console.warn('PubChem lookup failed for:', smiles.substring(0, 30), error);
    return result;
  }
}

/**
 * Look up multiple molecules in parallel
 * Limits concurrency to avoid rate limiting
 */
export async function lookupMultipleMolecules(
  smilesList: string[],
  maxConcurrency: number = 3
): Promise<Map<string, MoleculeInfo>> {
  const results = new Map<string, MoleculeInfo>();

  // Process in batches to avoid rate limiting
  for (let i = 0; i < smilesList.length; i += maxConcurrency) {
    const batch = smilesList.slice(i, i + maxConcurrency);
    const batchResults = await Promise.all(
      batch.map((smiles) => lookupMoleculeBySmiles(smiles))
    );

    for (const result of batchResults) {
      results.set(result.smiles, result);
    }

    // Small delay between batches to be nice to PubChem
    if (i + maxConcurrency < smilesList.length) {
      await new Promise((resolve) => setTimeout(resolve, 200));
    }
  }

  return results;
}

/**
 * Format molecule name for display
 * Returns common name if available, otherwise truncated SMILES
 */
export function formatMoleculeName(info: MoleculeInfo | undefined, smiles: string): string {
  if (info?.name && info.isKnownDrug) {
    return info.name;
  }
  if (info?.name && info.name.length < 40) {
    return info.name;
  }
  // Fallback to truncated SMILES
  return smiles.length > 30 ? smiles.substring(0, 30) + '...' : smiles;
}
