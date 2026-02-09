// Mock data for demo mode
// Pre-generated realistic responses for offline demonstration

import type { StructurePredictionResult } from '../services/structurePrediction';
import type { GeneratedMolecule } from '../services/moleculeGeneration';
import type { DockingResult } from '../services/docking';

// ============================================
// Mock Protein Data (UniProt-like responses)
// ============================================

export interface MockProteinData {
  accession: string;
  name: string;
  organism: string;
  sequence: string;
  length: number;
}

export const MOCK_PROTEINS: Record<string, MockProteinData> = {
  P35354: {
    accession: 'P35354',
    name: 'Prostaglandin G/H synthase 2 (COX-2)',
    organism: 'Homo sapiens',
    sequence: 'MLARALLLCAVLALSHTANPCCSHPCQNRGVCMSVGFDQYKCDCTRTGFYGENCSTPEFLTRIKLFLKPTPNTVHYILTHFKGFWNVVNNIPFLRNAIMSYVLTSRSHLIDSPPTYNADYGYKSWEAFSNLSYYTRALPPVPDDCPTPLGVKGKKQLPDSNEIVEKLLLRRKFIPDPQGSNMMFAFFAQHFTHQFFKTSGKMGPGFTKALGHGVDLGHIYGDNLERQYQLRLFKDGKLKYQVLDGEMYPPSVEEAPVLMHYPRGIPPQSQMAVGQEVFGLLPGLMLYATIWLREHNRVCDLLKAEHPTWGDEQLFQTT',
    length: 604,
  },
  P00519: {
    accession: 'P00519',
    name: 'Tyrosine-protein kinase ABL1',
    organism: 'Homo sapiens',
    sequence: 'ITMKHKLGGGQYGEVYEGVWKKYSLTVAVKTLKEDTMEVEEFLKEAAVMKEIKHPNLVQLLGVCTREPPFYIITEFMTYGNLLDYLRECNRQEVNAVVLLYMATQISSAMEYLEKKNFIHRDLAARNCLVGENHLVKVADFGLSRLMTGDTYTAHAGAKFPIKWTAPESLAYNKFSIKSDVWAFGVLLWEIATYGMSPYPGIDLSQVYELLEKDYRMERPEGCPEKVYELMRACWQWNPSDRPSFAEIHQAFETMFQESSISDEVEKELGKQGVRGAVSTLLQAPELPTKTRTSRRAAEHRDTTDVPEMPHSKGQGESDPLDHEPAVSPLLPRKERGPPEGGLNEDERLLPKDKKTNLFSALIKKKKKTAPTPPKRSSSFREMDGQPERRGAGEEEGRDISNGALAFTPLDTADPAKSPKPSNGAGVPNGALRESGGSGFRSPHLWKKSSTLTSSRLATGEEEGGGSSSKRFLRSCSASCVPHGAKDTEWRSVTLPRDLQSTGRQFDSSTFGGHKSEKPALPRKRAGENRSDQVTRGTVTPPPRLVKKNEEAADEVFKDIMESSPGSSPPNLTPKPLRRQVTVAPASGLPHKEEAGKGSALGTPAAAEPVTPTSKAGSGAPGGTSKGPAEESRVRRHKHSSESPGRDKGKLSRLKPAPPPPPAASAGKAGGKPSQSPSQEAAGEAVLGAKTKATSLVDAVNSDAAKPSQPGEGLKKPVLPATPKPQSAKPSGTPISPAPVPSTLPSASSALAGDQPSSTAFIPLISTRVSLRKTRQPPERIASGAITKGVVLDSTEALCLAISRNSEQMASHSAVLEAGKNLYTFCVSYVDSIQQMRNKFAFREAINKLENNLRELQICPATAGSGPAATQDFSKLLSSVKEISDIVQR',
    length: 1130,
  },
  P0DTD1: {
    accession: 'P0DTD1',
    name: 'SARS-CoV-2 Main protease (Mpro)',
    organism: 'Severe acute respiratory syndrome coronavirus 2',
    sequence: 'SGFRKMAFPSGKVEGCMVQVTCGTTTLNGLWLDDVVYCPRHVICTSEDMLNPNYEDLLIRKSNHNFLVQAGNVQLRVIGHSMQNCVLKLKVDTANPKTPKYKFVRIQPGQTFSVLACYNGSPSGVYQCAMRPNFTIKGSFLNGSCGSVGFNIDYDCVSFCYMHHMELPTGVHAGTDLEGNFYGPFVDRQTAQAAGTDTTITVNVLAWLYAAVINGDRWFLNRFTTTLNDFNLVAMKYNYEPLTQDHVDILGPLSAQTGIAVLDMCASLKELLQNGMNGRTILGSALLEDEFTPFDVVRQCSGVTFQ',
    length: 306,
  },
  Q13131: {
    accession: 'Q13131',
    name: 'AMP-activated protein kinase catalytic subunit alpha-1',
    organism: 'Homo sapiens',
    sequence: 'MAEKQKHDGRVKIGHYILGDTLGVGTFGKVKVGKHELTGHKVAVKILNRQKIRSLDVVGKIRREIQNLKLFRHPHIIKLYQVISTPSDIFMVMEYVSGGELFERIIDCDFRFYMSNTGYLNVVMEYVPGGEMFSHLRRIGRFSEPHARFYAAQIVLTFEYLHSLDLIYRDLKPENLLIDQQGYIQVTDFGFAKRVKGRTWTLCGTPEYLAPEIILSKGYNKAVDWWALGVLIYEMAAGYPPFFADQPIQIYEKIVSGKVRFPSHFSSDLKDLLRNLLQVDLTKRFGNLKDFGVFNHTPDGKEVQKIIRQYQLDATGHNYPISNRLQELLVPK',
    length: 559,
  },
};

// ============================================
// Mock Structure Data (PDB format snippets)
// ============================================

// Simplified PDB structure for COX-2 (demo purposes)
const MOCK_COX2_STRUCTURE = `HEADER    OXIDOREDUCTASE                          01-JAN-00   MOCK
TITLE     MOCK COX-2 STRUCTURE FOR DEMO
COMPND    MOL_ID: 1;
COMPND   2 MOLECULE: PROSTAGLANDIN G/H SYNTHASE 2;
COMPND   3 CHAIN: A
ATOM      1  N   MET A   1      -8.123  12.456   3.789  1.00 45.23           N
ATOM      2  CA  MET A   1      -7.234  11.345   4.567  1.00 44.12           C
ATOM      3  C   MET A   1      -6.123  10.234   3.456  1.00 43.01           C
ATOM      4  O   MET A   1      -5.012   9.123   2.345  1.00 42.90           O
ATOM      5  CB  MET A   1      -8.345  10.456   5.678  1.00 41.89           C
ATOM      6  N   LEU A   2      -6.234  10.567   2.234  1.00 40.78           N
ATOM      7  CA  LEU A   2      -5.123   9.456   1.123  1.00 39.67           C
ATOM      8  C   LEU A   2      -4.012   8.345   0.012  1.00 38.56           C
ATOM      9  O   LEU A   2      -2.901   7.234  -1.099  1.00 37.45           O
ATOM     10  CB  LEU A   2      -6.234   8.567   2.234  1.00 36.34           C
ATOM     11  N   ALA A   3      -4.123   8.678  -1.210  1.00 35.23           N
ATOM     12  CA  ALA A   3      -3.012   7.567  -2.321  1.00 34.12           C
ATOM     13  C   ALA A   3      -1.901   6.456  -3.432  1.00 33.01           C
ATOM     14  O   ALA A   3      -0.790   5.345  -4.543  1.00 32.90           O
ATOM     15  CB  ALA A   3      -4.123   6.678  -1.210  1.00 31.89           C
END
`;

// Simplified PDB structure for ABL1 kinase
const MOCK_ABL1_STRUCTURE = `HEADER    TRANSFERASE                             01-JAN-00   MOCK
TITLE     MOCK ABL1 KINASE STRUCTURE FOR DEMO
COMPND    MOL_ID: 1;
COMPND   2 MOLECULE: TYROSINE-PROTEIN KINASE ABL1;
COMPND   3 CHAIN: A
ATOM      1  N   ILE A   1      -5.234  15.678   6.789  1.00 52.34           N
ATOM      2  CA  ILE A   1      -4.123  14.567   7.890  1.00 51.23           C
ATOM      3  C   ILE A   1      -3.012  13.456   8.901  1.00 50.12           C
ATOM      4  O   ILE A   1      -1.901  12.345   9.012  1.00 49.01           O
ATOM      5  CB  ILE A   1      -5.234  13.678   6.789  1.00 48.90           C
ATOM      6  N   THR A   2      -3.123  13.789   10.123  1.00 47.89           N
ATOM      7  CA  THR A   2      -2.012  12.678   11.234  1.00 46.78           C
ATOM      8  C   THR A   2      -0.901  11.567   12.345  1.00 45.67           C
ATOM      9  O   THR A   2       0.210  10.456   13.456  1.00 44.56           O
ATOM     10  CB  THR A   2      -3.123  11.789   10.123  1.00 43.45           C
END
`;

// Simplified PDB structure for SARS-CoV-2 Mpro
const MOCK_MPRO_STRUCTURE = `HEADER    HYDROLASE                               01-JAN-00   MOCK
TITLE     MOCK SARS-COV-2 MPRO STRUCTURE FOR DEMO
COMPND    MOL_ID: 1;
COMPND   2 MOLECULE: 3C-LIKE PROTEINASE;
COMPND   3 CHAIN: A
ATOM      1  N   SER A   1      -2.345  18.901   9.012  1.00 58.45           N
ATOM      2  CA  SER A   1      -1.234  17.890  10.123  1.00 57.34           C
ATOM      3  C   SER A   1      -0.123  16.789  11.234  1.00 56.23           C
ATOM      4  O   SER A   1       0.988  15.678  12.345  1.00 55.12           O
ATOM      5  CB  SER A   1      -2.345  16.901   9.012  1.00 54.01           C
ATOM      6  N   GLY A   2      -0.234  17.012  12.456  1.00 53.90           N
ATOM      7  CA  GLY A   2       0.877  15.901  13.567  1.00 52.89           C
ATOM      8  C   GLY A   2       1.988  14.790  14.678  1.00 51.78           C
ATOM      9  O   GLY A   2       3.099  13.679  15.789  1.00 50.67           O
END
`;

export const MOCK_STRUCTURES: Record<string, { structure: string; format: 'pdb' | 'cif' }> = {
  P35354: { structure: MOCK_COX2_STRUCTURE, format: 'pdb' },
  P00519: { structure: MOCK_ABL1_STRUCTURE, format: 'pdb' },
  P0DTD1: { structure: MOCK_MPRO_STRUCTURE, format: 'pdb' },
  Q13131: { structure: MOCK_ABL1_STRUCTURE, format: 'pdb' }, // Reuse for demo
};

// ============================================
// Mock Structure Prediction Results
// ============================================

export function getMockStructurePrediction(
  sequence: string,
  model: string = 'openfold3'
): StructurePredictionResult {
  // Find matching protein by sequence prefix
  const proteinId = Object.keys(MOCK_PROTEINS).find(
    (id) => MOCK_PROTEINS[id].sequence.startsWith(sequence.slice(0, 50))
  );

  const mockStructure = proteinId ? MOCK_STRUCTURES[proteinId] : MOCK_STRUCTURES.P35354;

  return {
    structure: mockStructure.structure,
    format: mockStructure.format,
    confidenceScore: 0.85 + Math.random() * 0.1, // 0.85-0.95
    plddt: 78 + Math.random() * 15, // 78-93
    ptm: 0.75 + Math.random() * 0.15, // 0.75-0.90
    modelUsed: model === 'openfold3' ? 'OpenFold3' : model === 'boltz2' ? 'Boltz2' : 'OpenFold2',
    elapsedTime: 2000 + Math.random() * 3000, // 2-5 seconds simulated
  };
}

// ============================================
// Mock Generated Molecules
// ============================================

// Ibuprofen analogs (for COX-2 demo)
export const MOCK_IBUPROFEN_ANALOGS: GeneratedMolecule[] = [
  { smiles: 'CC(C)Cc1ccc(cc1)C(C)C(=O)O', score: 0.98 }, // Ibuprofen itself
  { smiles: 'CC(C)Cc1ccc(cc1)C(C)C(=O)N', score: 0.92 },
  { smiles: 'CC(C)Cc1ccc(F)(cc1)C(C)C(=O)O', score: 0.89 },
  { smiles: 'CC(C)Cc1ccc(cc1)C(CC)C(=O)O', score: 0.87 },
  { smiles: 'CC(C)Cc1ccc(Cl)(cc1)C(C)C(=O)O', score: 0.85 },
  { smiles: 'CCC(C)c1ccc(cc1)C(C)C(=O)O', score: 0.84 },
  { smiles: 'CC(C)Cc1ccc(cc1)C(C)C(=O)OC', score: 0.82 },
  { smiles: 'CC(C)Cc1ccc(cc1)CC(=O)O', score: 0.80 },
  { smiles: 'CC(C)c1ccc(cc1)C(C)C(=O)O', score: 0.79 },
  { smiles: 'CC(C)Cc1ccc(O)(cc1)C(C)C(=O)O', score: 0.77 },
  { smiles: 'CC(C)Cc1cccc(c1)C(C)C(=O)O', score: 0.75 },
  { smiles: 'CC(C)Cc1ccc(cc1)C(C)(C)C(=O)O', score: 0.73 },
  { smiles: 'CC(C)Cc1ccc(cc1)C(=O)C(=O)O', score: 0.71 },
  { smiles: 'CC(C)Cc1ccc(N)(cc1)C(C)C(=O)O', score: 0.69 },
  { smiles: 'CC(C)Cc1ccc(cc1)C(C)C(=O)NC', score: 0.67 },
  { smiles: 'COc1ccc(cc1)C(C)Cc1ccccc1', score: 0.65 },
  { smiles: 'CC(C)Cc1ccc(cc1)C(C)C(=S)O', score: 0.63 },
  { smiles: 'CC(C)Cc1ccc(cc1)C(C)P(=O)(O)O', score: 0.61 },
  { smiles: 'FC(F)(F)c1ccc(cc1)C(C)C(=O)O', score: 0.59 },
  { smiles: 'CC(C)Cc1ccc(cc1)C(C)C(=O)S', score: 0.57 },
];

// Imatinib analogs (for BCR-ABL demo)
export const MOCK_IMATINIB_ANALOGS: GeneratedMolecule[] = [
  { smiles: 'Cc1ccc(cc1Nc2nccc(n2)c3cccnc3)NC(=O)c4ccc(cc4)CN5CCN(CC5)C', score: 0.97 },
  { smiles: 'Cc1ccc(cc1Nc2nccc(n2)c3cccnc3)NC(=O)c4ccc(F)(cc4)CN5CCN(CC5)C', score: 0.91 },
  { smiles: 'Cc1ccc(cc1Nc2nccc(n2)c3cccnc3)NC(=O)c4ccc(cc4)CN5CCOCC5', score: 0.88 },
  { smiles: 'Fc1ccc(cc1Nc2nccc(n2)c3cccnc3)NC(=O)c4ccc(cc4)CN5CCN(CC5)C', score: 0.85 },
  { smiles: 'Cc1ccc(cc1Nc2nccc(n2)c3ccncc3)NC(=O)c4ccc(cc4)CN5CCN(CC5)C', score: 0.83 },
  { smiles: 'Cc1ccc(cc1Nc2ncc(n2)c3cccnc3)NC(=O)c4ccc(cc4)CN5CCN(CC5)C', score: 0.81 },
  { smiles: 'Cc1ccc(cc1Nc2nccc(n2)c3cccnc3)NC(=O)c4ccc(cc4)N5CCN(CC5)C', score: 0.79 },
  { smiles: 'Cc1ccc(cc1Nc2nccc(n2)c3cccnc3)NC(=O)c4cccc(c4)CN5CCN(CC5)C', score: 0.77 },
  { smiles: 'Cc1cc(Nc2nccc(n2)c3cccnc3)ccc1NC(=O)c4ccc(cc4)CN5CCN(CC5)C', score: 0.75 },
  { smiles: 'Cc1ccc(cc1Nc2nccc(n2)c3cccnc3)NC(=O)c4ccc(Cl)(cc4)CN5CCN(CC5)C', score: 0.73 },
];

// Nirmatrelvir-like analogs (for COVID Mpro demo)
export const MOCK_MPRO_ANALOGS: GeneratedMolecule[] = [
  { smiles: 'CC(C)(C)c1cc(C(=O)Nc2ccc(C#N)cn2)cc(C(C)(C)C)c1O', score: 0.95 },
  { smiles: 'CC(C)(C)c1cc(C(=O)Nc2ccc(C#N)cc2)cc(C(C)(C)C)c1O', score: 0.89 },
  { smiles: 'CC(C)(C)c1cc(C(=O)Nc2ncc(C#N)cn2)cc(C(C)(C)C)c1O', score: 0.86 },
  { smiles: 'CC(C)c1cc(C(=O)Nc2ccc(C#N)cn2)cc(C(C)C)c1O', score: 0.83 },
  { smiles: 'CC(C)(C)c1cc(C(=O)Nc2ccc(F)cn2)cc(C(C)(C)C)c1O', score: 0.80 },
  { smiles: 'CC(C)(C)c1cc(C(=O)Nc2ccc(C(F)(F)F)cn2)cc(C(C)(C)C)c1O', score: 0.77 },
  { smiles: 'CC(C)(C)c1cc(C(=O)Nc2ccnc(C#N)c2)cc(C(C)(C)C)c1O', score: 0.74 },
  { smiles: 'Cc1cc(C(=O)Nc2ccc(C#N)cn2)cc(C)c1O', score: 0.71 },
  { smiles: 'CC(C)(C)c1cc(C(=O)Nc2ccc(C#N)cn2)cc(C(C)(C)C)c1', score: 0.68 },
  { smiles: 'CC(C)(C)c1cc(C(=O)Nc2ccc(Br)cn2)cc(C(C)(C)C)c1O', score: 0.65 },
];

export function getMockMolecules(seedSmiles: string, count: number = 20): GeneratedMolecule[] {
  // Select appropriate mock molecules based on seed
  let molecules: GeneratedMolecule[];

  if (seedSmiles.includes('Cc1ccc(cc1)C(C)C(=O)O') || seedSmiles.includes('ibuprofen')) {
    molecules = MOCK_IBUPROFEN_ANALOGS;
  } else if (seedSmiles.includes('nccc(n2)') || seedSmiles.includes('imatinib')) {
    molecules = MOCK_IMATINIB_ANALOGS;
  } else if (seedSmiles.includes('C#N') || seedSmiles.includes('nirmatrelvir')) {
    molecules = MOCK_MPRO_ANALOGS;
  } else {
    // Default to ibuprofen analogs
    molecules = MOCK_IBUPROFEN_ANALOGS;
  }

  // Return requested count with slight score variations
  return molecules.slice(0, count).map((mol) => ({
    ...mol,
    score: Math.max(0.1, Math.min(1, mol.score + (Math.random() - 0.5) * 0.05)),
  }));
}

// ============================================
// Mock Docking Results
// ============================================

export function getMockDockingResults(
  ligandSmiles: string | string[],
  _proteinStructure?: string
): DockingResult[] {
  const smilesList = Array.isArray(ligandSmiles)
    ? ligandSmiles
    : ligandSmiles.split(',').map((s) => s.trim());

  return smilesList.slice(0, 10).map((smiles, index) => ({
    ligandSmiles: smiles,
    poses: [
      {
        ligand_positions: `MOCK_SDF_POSE_${index + 1}`,
        confidence: 0.85 - index * 0.05 + Math.random() * 0.1,
        position_confidence: 0.9 - index * 0.03,
      },
      {
        ligand_positions: `MOCK_SDF_POSE_${index + 1}_ALT`,
        confidence: 0.75 - index * 0.05 + Math.random() * 0.1,
        position_confidence: 0.8 - index * 0.03,
      },
    ],
    bestConfidence: 0.85 - index * 0.05 + Math.random() * 0.1,
    elapsedTime: 1500 + Math.random() * 2000,
  }));
}

// ============================================
// Mock Protein Design Results (RFDiffusion)
// ============================================

export interface MockProteinDesignResult {
  structure: string;
  mode: string;
  length: number;
}

export function getMockProteinDesign(
  mode: string,
  length: number,
  _targetStructure?: string
): MockProteinDesignResult {
  return {
    structure: MOCK_ABL1_STRUCTURE, // Simplified mock
    mode,
    length,
  };
}

// ============================================
// Mock Sequence Design Results (ProteinMPNN)
// ============================================

export interface MockSequenceDesignResult {
  sequences: string[];
  scores: number[];
  numDesigns: number;
}

export function getMockSequenceDesign(
  _structure: string,
  numSequences: number = 4
): MockSequenceDesignResult {
  const mockSequences = [
    'MKVLWAALLVTFLAGCQAKVEQAVETEPEPELRQQTEWQSGQRWELALGRFWDYLRWVQTLSEQVQEELLSSQVTQEL',
    'MKVLWAALLVTFLAGCQAKVEQAVETEPEPELRQQTEWQSGQRWELALGRFWDYLRWVQTLSEQVQEELLSSQVTQEL',
    'MKYLWAALLVTFLAGCQAKVEQAVETEPEPELRQQTEWQSGQRWELALGRFWDYLRWVQTLSEQVQEELLSSQVTQEL',
    'MKVLWAALLVTFLAGCQAKVEQAVETEPEPELRQQTEWQSGQRWDLALGRFWDYLRWVQTLSEQVQEELLSSQVTQEL',
  ];

  return {
    sequences: mockSequences.slice(0, numSequences),
    scores: Array.from({ length: numSequences }, (_, i) => 0.95 - i * 0.05 + Math.random() * 0.02),
    numDesigns: numSequences,
  };
}

// ============================================
// Mock LLM Responses for Agent
// ============================================

export const MOCK_AGENT_RESPONSES: Record<string, string> = {
  // Initial analysis response
  initial_analysis: `I'll help you with this drug discovery task. Let me analyze the requirements and design an appropriate workflow.

Based on your request, I'll use the following approach:
1. First, I'll search for the target protein sequence in UniProt
2. Then predict the 3D structure using OpenFold3
3. Generate candidate molecules using MolMIM
4. Dock the candidates to evaluate binding
5. Analyze similarity to the reference compound

Let me start by searching for the protein target.`,

  // After protein search
  protein_found: `I found the target protein in UniProt. The protein has been retrieved successfully with its full sequence and metadata.

Now I'll predict the 3D structure using OpenFold3, which provides excellent accuracy for structure prediction.`,

  // After structure prediction
  structure_predicted: `The structure prediction is complete with high confidence (pLDDT > 80). The predicted structure shows a well-folded protein with clear binding pockets.

Next, I'll generate candidate molecules that could potentially bind to this target.`,

  // After molecule generation
  molecules_generated: `I've generated a diverse set of candidate molecules using MolMIM. The molecules show good drug-likeness scores and structural diversity around the seed compound.

Now I'll perform molecular docking to predict how these candidates bind to the target protein.`,

  // After docking
  docking_complete: `Docking analysis is complete. Several candidates show promising binding affinity with confidence scores above 0.7.

Let me calculate the similarity of these candidates to the reference compound and summarize the findings.`,

  // Final summary
  complete_summary: `## Drug Discovery Summary

### Target Analysis
- Successfully identified and characterized the protein target
- Structure prediction achieved high confidence (pLDDT: ~85)

### Candidate Generation
- Generated 20 novel candidate molecules
- Candidates show good drug-likeness properties

### Binding Analysis
- Top candidates show strong predicted binding affinity
- Best docking confidence: ~0.85

### Recommendations
1. **Top Candidates**: Molecules ranked 1-5 show the most promise
2. **Next Steps**: Consider experimental validation of top hits
3. **Optimization**: Further SAR exploration around top scaffolds

This demonstrates how AI can accelerate the early drug discovery process.`,
};

// ============================================
// Demo Mode Delays (simulate API latency)
// ============================================

export const DEMO_DELAYS = {
  proteinSearch: 800,
  structurePrediction: 2500,
  moleculeGeneration: 1800,
  docking: 2200,
  similarity: 500,
  llmResponse: 1200,
};

export async function simulateDelay(operation: keyof typeof DEMO_DELAYS): Promise<void> {
  const baseDelay = DEMO_DELAYS[operation];
  const jitter = baseDelay * 0.2 * (Math.random() - 0.5);
  await new Promise((resolve) => setTimeout(resolve, baseDelay + jitter));
}
