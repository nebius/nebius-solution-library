// Demo Service
// Provides mock responses when demo mode is enabled

import {
  MOCK_PROTEINS,
  getMockStructurePrediction,
  getMockMolecules,
  getMockDockingResults,
  getMockProteinDesign,
  getMockSequenceDesign,
  MOCK_AGENT_RESPONSES,
  simulateDelay,
  type MockProteinData,
} from '../data/mockData';
import type { StructurePredictionResult } from './structurePrediction';
import type { GeneratedMolecule, MoleculeGenerationResult } from './moleculeGeneration';
import type { DockingResult } from './docking';

// Demo mode state
let demoModeEnabled = false;

export function setDemoMode(enabled: boolean): void {
  demoModeEnabled = enabled;
  console.log(`Demo mode ${enabled ? 'enabled' : 'disabled'}`);
}

export function isDemoMode(): boolean {
  return demoModeEnabled;
}

// ============================================
// Mock UniProt Service
// ============================================

export async function demoFetchSequence(accessionOrQuery: string): Promise<MockProteinData | null> {
  await simulateDelay('proteinSearch');

  // Check if it's a direct accession match
  const upperQuery = accessionOrQuery.toUpperCase();
  if (MOCK_PROTEINS[upperQuery]) {
    return MOCK_PROTEINS[upperQuery];
  }

  // Search by name or partial match
  for (const [accession, protein] of Object.entries(MOCK_PROTEINS)) {
    if (
      protein.name.toLowerCase().includes(accessionOrQuery.toLowerCase()) ||
      accession.toLowerCase().includes(accessionOrQuery.toLowerCase())
    ) {
      return protein;
    }
  }

  // Default to COX-2 if no match found
  return MOCK_PROTEINS.P35354;
}

export async function demoSearchProteins(
  query: string,
  _limit: number = 5
): Promise<Array<{ accession: string; name: string; organism: string }>> {
  await simulateDelay('proteinSearch');

  const results: Array<{ accession: string; name: string; organism: string }> = [];
  const lowerQuery = query.toLowerCase();

  for (const [accession, protein] of Object.entries(MOCK_PROTEINS)) {
    if (
      protein.name.toLowerCase().includes(lowerQuery) ||
      accession.toLowerCase().includes(lowerQuery)
    ) {
      results.push({
        accession,
        name: protein.name,
        organism: protein.organism,
      });
    }
  }

  // If no results, return first protein as demo
  if (results.length === 0) {
    const firstProtein = Object.entries(MOCK_PROTEINS)[0];
    results.push({
      accession: firstProtein[0],
      name: firstProtein[1].name,
      organism: firstProtein[1].organism,
    });
  }

  return results;
}

// ============================================
// Mock Structure Prediction Service
// ============================================

export async function demoPredictStructure(
  sequence: string,
  model: string = 'openfold3'
): Promise<StructurePredictionResult> {
  await simulateDelay('structurePrediction');
  return getMockStructurePrediction(sequence, model);
}

// ============================================
// Mock Molecule Generation Service
// ============================================

export async function demoGenerateMolecules(
  seedSmiles: string,
  numMolecules: number = 20
): Promise<MoleculeGenerationResult> {
  await simulateDelay('moleculeGeneration');

  const molecules = getMockMolecules(seedSmiles, numMolecules);

  return {
    molecules,
    modelUsed: 'MolMIM',
    elapsedTime: 1800,
  };
}

// ============================================
// Mock Docking Service
// ============================================

export async function demoDockLigand(
  _proteinStructure: string,
  _structureFormat: string,
  ligandSmiles: string,
  _numPoses: number = 5
): Promise<DockingResult> {
  await simulateDelay('docking');

  const results = getMockDockingResults(ligandSmiles);
  return results[0];
}

export async function demoDockMultipleLigands(
  _proteinStructure: string,
  _structureFormat: string,
  ligandSmilesList: string[]
): Promise<DockingResult[]> {
  await simulateDelay('docking');
  return getMockDockingResults(ligandSmilesList);
}

// ============================================
// Mock Protein Design Service (RFDiffusion)
// ============================================

export async function demoDesignProtein(
  mode: string,
  length: number,
  targetStructure?: string
): Promise<{ structure: string; mode: string; length: number }> {
  await simulateDelay('structurePrediction');
  return getMockProteinDesign(mode, length, targetStructure);
}

// ============================================
// Mock Sequence Design Service (ProteinMPNN)
// ============================================

export async function demoDesignSequence(
  structure: string,
  numSequences: number = 4
): Promise<{ sequences: string[]; scores: number[]; numDesigns: number }> {
  await simulateDelay('moleculeGeneration');
  return getMockSequenceDesign(structure, numSequences);
}

// ============================================
// Mock LLM Chat Service
// ============================================

// Mock research plan for step-by-step mode
function getMockResearchPlan(drugName: string, uniprotId: string): string {
  return `## 1. Objective Summary

Design and discover novel small-molecule therapeutics targeting ${drugName || 'the specified protein'} for therapeutic intervention.

## 2. Task Classification

**Small molecule drug discovery** - This is a target-based drug discovery workflow focused on finding compounds that modulate the target protein's activity.

## 3. Target Information

- **Name:** ${drugName || 'Target Protein'}
- **UniProt ID:** ${uniprotId}
- **Type:** Protein
- **Key features:** Active site with druggable binding pocket suitable for small molecule intervention

## 4. Recommended Workflow

| Step | Model | Purpose |
|------|-------|---------|
| 1 | UniProt Fetch | Retrieve target protein sequence |
| 2 | OpenFold3 | Predict 3D structure of target protein |
| 3 | MolMIM | Generate candidate molecules around seed compound |
| 4 | DiffDock | Dock candidates and predict binding poses |
| 5 | Analysis | Evaluate drug-likeness and similarity |

## 5. Key Considerations

- **Structural accuracy:** OpenFold3 provides reliable predictions for most proteins
- **Chemical diversity:** MolMIM explores chemical space around known active compounds
- **Binding validation:** DiffDock confidence scores indicate binding likelihood
- **Alternative:** If structure prediction fails, consider using experimental structures from PDB

## 6. Success Criteria

- Structure prediction with pLDDT > 70
- Generate 20+ diverse candidate molecules
- Identify candidates with docking confidence > 0.6
- Top candidates should maintain drug-like properties (Lipinski Ro5)`;
}

export async function* demoStreamChat(
  _messages: Array<{ role: string; content: string }>
): AsyncGenerator<string, void, unknown> {
  await simulateDelay('llmResponse');

  // Check if this is a research planning request (step-by-step mode)
  const systemMessage = _messages.find((m) => m.role === 'system')?.content || '';
  const lastUserMessage = _messages.filter((m) => m.role === 'user').pop()?.content || '';
  const lowerMessage = lastUserMessage.toLowerCase();

  // Detect if this is the AI Planning step (has specific system prompt)
  if (systemMessage.includes('create a detailed research plan') || systemMessage.includes('Task Classification')) {
    // Extract drug/target info from the user message
    let drugName = 'Target Protein';
    let uniprotId = 'P35354';

    if (lowerMessage.includes('cox-2') || lowerMessage.includes('ibuprofen') || lowerMessage.includes('prostaglandin')) {
      drugName = 'COX-2 (Prostaglandin G/H synthase 2)';
      uniprotId = 'P35354';
    } else if (lowerMessage.includes('abl') || lowerMessage.includes('imatinib') || lowerMessage.includes('kinase') || lowerMessage.includes('leukemia')) {
      drugName = 'ABL1 Tyrosine Kinase';
      uniprotId = 'P00519';
    } else if (lowerMessage.includes('mpro') || lowerMessage.includes('covid') || lowerMessage.includes('sars') || lowerMessage.includes('protease')) {
      drugName = 'SARS-CoV-2 Main Protease (Mpro)';
      uniprotId = 'P0DTD1';
    } else if (lowerMessage.includes('ampk') || lowerMessage.includes('metformin') || lowerMessage.includes('glucose')) {
      drugName = 'AMPK (AMP-activated protein kinase)';
      uniprotId = 'Q13131';
    }

    const plan = getMockResearchPlan(drugName, uniprotId);

    // Stream the plan
    const words = plan.split(' ');
    for (let i = 0; i < words.length; i++) {
      yield words.slice(0, i + 1).join(' ');
      await new Promise((resolve) => setTimeout(resolve, 15 + Math.random() * 10));
    }
    return;
  }

  // Otherwise, handle as agent chat
  let response: string;

  // Check if this is a tool result
  if (lowerMessage.includes('tool result')) {
    if (lowerMessage.includes('search_uniprot')) {
      response = `I found the target protein. Now I'll predict its 3D structure using OpenFold3, which provides excellent accuracy for structure prediction.

<tool_call>{"tool": "predict_structure", "arguments": {"sequence": "MLARALLLCAVLALSHTANPCCSHPCQNRGVCMSVGFDQYKCDCTRTGFYGENCSTPEFLTRIKLFLKPTPNTVHYILTHFKGFWNVVNNIPFLRNAIMSYVLTSRSHLIDSPPTYNADYGYKSWEAFSNLSYYTRALPPVPDDCPTPLGVKGKKQLPDSNEIVEKLLLRRKFIPDPQGSNMMFAFFAQHFTHQFFKTSGKMGPGFTKALGHGVDLGHIYGDNLERQYQLRLFKDGKLKYQVLDGEMYPPSVEEAPVLMHYPRGIPPQSQMAVGQEVFGLLPGLMLYATIWLREHNRVCDLLKAEHPTWGDEQLFQTT", "model": "openfold3"}}</tool_call>`;
    } else if (lowerMessage.includes('predict_structure')) {
      response = `Excellent! The structure prediction completed successfully with high confidence (pLDDT > 80). The predicted structure shows a well-folded protein with clear binding pockets.

Next, I'll generate candidate molecules using MolMIM that could potentially bind to this target.

<tool_call>{"tool": "generate_molecules", "arguments": {"seed_smiles": "CC(C)Cc1ccc(cc1)C(C)C(=O)O", "num_molecules": 20}}</tool_call>`;
    } else if (lowerMessage.includes('generate_molecules')) {
      response = `I've generated 20 diverse candidate molecules. They show good drug-likeness properties and structural diversity around the seed compound.

Now I'll perform molecular docking with DiffDock to predict how these candidates bind to the target protein.

<tool_call>{"tool": "dock_molecules", "arguments": {"ligand_smiles": "CC(C)Cc1ccc(cc1)C(C)C(=O)O,CC(C)Cc1ccc(cc1)C(C)C(=O)N,CC(C)Cc1ccc(F)(cc1)C(C)C(=O)O"}}</tool_call>`;
    } else if (lowerMessage.includes('dock_molecules') || lowerMessage.includes('dock')) {
      response = `Docking analysis is complete! Several candidates show promising binding affinity with confidence scores above 0.7.

Let me summarize the findings for you.

<tool_call>{"tool": "complete", "arguments": {"summary": "## Drug Discovery Summary\\n\\n### Target Analysis\\n- Successfully identified and characterized the protein target\\n- Structure prediction achieved high confidence (pLDDT: ~85)\\n\\n### Candidate Generation\\n- Generated 20 novel candidate molecules\\n- Candidates show good drug-likeness properties\\n\\n### Binding Analysis\\n- Top candidates show strong predicted binding affinity\\n- Best docking confidence: ~0.85\\n\\n### Recommendations\\n1. **Top Candidates**: Molecules ranked 1-5 show the most promise\\n2. **Next Steps**: Consider experimental validation of top hits\\n3. **Optimization**: Further SAR exploration around top scaffolds\\n\\nThis demonstrates how AI can accelerate the early drug discovery process."}}</tool_call>`;
    } else {
      response = MOCK_AGENT_RESPONSES.complete_summary;
    }
  } else {
    // Initial message - start the workflow
    // Extract potential protein target from the message
    let uniprotId = 'P35354'; // Default to COX-2
    if (lowerMessage.includes('cox-2') || lowerMessage.includes('ibuprofen')) {
      uniprotId = 'P35354';
    } else if (lowerMessage.includes('abl') || lowerMessage.includes('imatinib') || lowerMessage.includes('kinase')) {
      uniprotId = 'P00519';
    } else if (lowerMessage.includes('mpro') || lowerMessage.includes('covid') || lowerMessage.includes('sars')) {
      uniprotId = 'P0DTD1';
    } else if (lowerMessage.includes('ampk') || lowerMessage.includes('metformin')) {
      uniprotId = 'Q13131';
    }

    response = `I'll help you with this drug discovery task. Let me analyze the requirements and design an appropriate workflow.

Based on your request, I'll use the following approach:
1. First, I'll search for the target protein sequence in UniProt
2. Then predict the 3D structure using OpenFold3
3. Generate candidate molecules using MolMIM
4. Dock the candidates to evaluate binding
5. Summarize the findings

Let me start by searching for the protein target.

<tool_call>{"tool": "search_uniprot", "arguments": {"query": "${uniprotId}"}}</tool_call>`;
  }

  // Stream the response word by word with small delays
  const words = response.split(' ');
  for (let i = 0; i < words.length; i++) {
    yield words.slice(0, i + 1).join(' ');
    await new Promise((resolve) => setTimeout(resolve, 25 + Math.random() * 15));
  }
}

// ============================================
// Mock Health Check Service
// ============================================

export interface MockHealthResult {
  id: string;
  status: 'ready' | 'error' | 'unknown';
}

export async function demoCheckHealth(_endpoints: Array<{ id: string }>): Promise<MockHealthResult[]> {
  // In demo mode, all services appear ready
  await new Promise((resolve) => setTimeout(resolve, 500));

  return _endpoints.map((endpoint) => ({
    id: endpoint.id,
    status: 'ready' as const,
  }));
}

// ============================================
// Wrapper Functions with Demo Mode Check
// ============================================

// These are convenience wrappers that check demo mode
// The actual services should import and use these

export function shouldUseDemoMode(): boolean {
  return isDemoMode();
}

// Export mock molecules type for compatibility
export type { GeneratedMolecule };
