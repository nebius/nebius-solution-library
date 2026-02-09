// UniProt API service for fetching protein sequences

import { isDemoMode, demoFetchSequence, demoSearchProteins } from './demoService';

export interface UniProtEntry {
  accession: string;
  id: string;
  proteinName: string;
  geneName: string;
  organism: string;
  sequence: string;
  length: number;
}

/**
 * Fetch protein sequence from UniProt by accession ID
 * @param accession - UniProt accession ID (e.g., "P35354" for COX-2)
 */
export async function fetchSequence(accession: string): Promise<UniProtEntry> {
  // Clean up accession (remove whitespace, convert to uppercase)
  const cleanAccession = accession.trim().toUpperCase();

  // Check for demo mode
  if (isDemoMode()) {
    const mockData = await demoFetchSequence(cleanAccession);
    if (mockData) {
      return {
        accession: mockData.accession,
        id: mockData.accession,
        proteinName: mockData.name,
        geneName: '',
        organism: mockData.organism,
        sequence: mockData.sequence,
        length: mockData.length,
      };
    }
    throw new Error(`Protein not found in demo mode: ${cleanAccession}`);
  }

  // Fetch FASTA format for the sequence
  const fastaUrl = `https://rest.uniprot.org/uniprotkb/${cleanAccession}.fasta`;
  const fastaResponse = await fetch(fastaUrl);

  if (!fastaResponse.ok) {
    if (fastaResponse.status === 404) {
      throw new Error(`Protein not found: ${cleanAccession}`);
    }
    throw new Error(`UniProt API error: ${fastaResponse.status}`);
  }

  const fastaText = await fastaResponse.text();
  const { header, sequence } = parseFasta(fastaText);

  // Fetch JSON for additional metadata
  const jsonUrl = `https://rest.uniprot.org/uniprotkb/${cleanAccession}.json`;
  const jsonResponse = await fetch(jsonUrl);

  let proteinName = '';
  let geneName = '';
  let organism = '';

  if (jsonResponse.ok) {
    const data = await jsonResponse.json();
    proteinName =
      data.proteinDescription?.recommendedName?.fullName?.value ||
      data.proteinDescription?.submissionNames?.[0]?.fullName?.value ||
      header;
    geneName = data.genes?.[0]?.geneName?.value || '';
    organism = data.organism?.scientificName || '';
  }

  return {
    accession: cleanAccession,
    id: header.split('|')[1] || cleanAccession,
    proteinName,
    geneName,
    organism,
    sequence,
    length: sequence.length,
  };
}

/**
 * Search UniProt for proteins by name or keyword
 * @param query - Search query (protein name, gene name, etc.)
 * @param limit - Maximum number of results
 */
export async function searchProteins(
  query: string,
  limit: number = 10
): Promise<Array<{ accession: string; name: string; organism: string }>> {
  // Check for demo mode
  if (isDemoMode()) {
    return demoSearchProteins(query, limit);
  }

  const encodedQuery = encodeURIComponent(query);
  const url = `https://rest.uniprot.org/uniprotkb/search?query=${encodedQuery}&format=json&size=${limit}`;

  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(`UniProt search error: ${response.status}`);
  }

  const data = await response.json();

  return data.results.map((entry: any) => ({
    accession: entry.primaryAccession,
    name:
      entry.proteinDescription?.recommendedName?.fullName?.value ||
      entry.proteinDescription?.submissionNames?.[0]?.fullName?.value ||
      'Unknown',
    organism: entry.organism?.scientificName || 'Unknown',
  }));
}

/**
 * Parse FASTA format string
 */
function parseFasta(fasta: string): { header: string; sequence: string } {
  const lines = fasta.trim().split('\n');
  const header = lines[0].startsWith('>') ? lines[0].substring(1) : lines[0];
  const sequence = lines
    .slice(1)
    .join('')
    .replace(/\s/g, '');

  return { header, sequence };
}

/**
 * Format sequence for display (add line breaks every N characters)
 */
export function formatSequence(sequence: string, lineLength: number = 60): string {
  const lines: string[] = [];
  for (let i = 0; i < sequence.length; i += lineLength) {
    lines.push(sequence.substring(i, i + lineLength));
  }
  return lines.join('\n');
}

/**
 * Validate if a string looks like a UniProt accession
 * UniProt accessions are typically 6 or 10 alphanumeric characters
 */
export function isValidAccession(accession: string): boolean {
  const pattern = /^[A-Z0-9]{6,10}$/i;
  return pattern.test(accession.trim());
}
