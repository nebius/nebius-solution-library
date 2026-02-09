# Drug Discovery Demo - Architecture Documentation

## Overview

This application is an interactive React-based demo showcasing AI-driven drug discovery workflows using NVIDIA NIMs (NVIDIA Inference Microservices) on Nebius AI Cloud. It demonstrates multiple computational biology pipelines including small molecule discovery, protein design, and protein binder design.

## Application Modes

### 1. Agent Mode (Default)
- **Component**: `AgentChat.tsx`
- **Description**: An AI-powered conversational interface that dynamically orchestrates the drug discovery workflow
- **How it works**:
  1. User describes their drug discovery goal
  2. Qwen3-80B LLM analyzes the request and determines the appropriate workflow
  3. Agent calls tools sequentially: UniProt search → Structure prediction → Molecule generation → Docking
  4. Results are streamed back with visualizations

### 2. Step-by-Step Mode
- **Component**: `App.tsx` with individual step components
- **Description**: Guided workflow where users manually progress through each step
- **Steps vary by workflow type** (see Workflow Types below)

## Workflow Types

### Small Molecule Discovery (`small-molecule`)
Traditional drug discovery targeting a protein:
1. **Use Case** - Select drug target (e.g., Ibuprofen → COX-2)
2. **AI Planning** - LLM creates research plan, identifies UniProt ID
3. **Sequence** - Fetch protein sequence from UniProt
4. **Structure** - Predict 3D structure (OpenFold3/Boltz2/OpenFold2)
5. **Molecules** - Generate candidate molecules (MolMIM/GenMol)
6. **Docking** - Predict binding poses (DiffDock)
7. **Rediscovery** - Score similarity to original drug
8. **Summary** - Results and insights

### Protein Binder Design (`protein-binder`)
Design proteins that bind to a target:
1. **Use Case** - Select binder target
2. **AI Planning** - Research plan
3. **Target Sequence** - Fetch target from UniProt
4. **Target Structure** - Predict target protein structure
5. **Binder Design** - Generate binder backbone (RFDiffusion)
6. **Sequence Design** - Design amino acid sequence (ProteinMPNN)
7. **Validation** - Verify fold with structure prediction
8. **Summary** - Results

### De Novo Protein Design (`de-novo-protein`)
Create new proteins from scratch:
1. **Use Case** - Define protein specifications
2. **AI Planning** - Research plan
3. **Structure Design** - Generate backbone (RFDiffusion)
4. **Sequence Design** - Design sequence (ProteinMPNN)
5. **Validation** - Verify folding
6. **Summary** - Results

### Enzyme Engineering (`enzyme-engineering`)
Analyze and potentially modify enzymes:
1. **Use Case** - Select enzyme
2. **AI Planning** - Research plan
3. **Sequence** - Fetch from UniProt
4. **Structure** - Predict structure
5. **Summary** - Analysis and insights

## Service Layer Architecture

```
src/services/
├── nimApi.ts          # Base API utilities (URL building, health checks, streaming chat)
├── agent.ts           # Agent loop with tool calling for dynamic workflows
├── agentTools.ts      # Tool definitions for the agent
├── structurePrediction.ts  # OpenFold3, Boltz2, OpenFold2 integrations
├── moleculeGeneration.ts   # MolMIM, GenMol molecule generation
├── docking.ts         # DiffDock molecular docking
├── uniprot.ts         # UniProt API integration
├── similarity.ts      # Tanimoto similarity calculation
├── msaSearch.ts       # MSA search for improved structure prediction
├── drugLikeness.ts    # Lipinski rules, QED calculations
├── demoService.ts     # Mock data service for demo mode
└── k8sService.ts      # Kubernetes scaling information
```

### Key Service Patterns

#### URL Building
All NIM endpoints use `buildNimUrl()` from `nimApi.ts`:
- **Development**: Routes through Vite proxy (`/api/nim-proxy/{host}/{port}{path}`)
- **Production**: Direct HTTP to `http://{gatewayUrl}:{port}{path}`

#### Demo Mode
When `demoModeEnabled` is true:
- All services check `isDemoMode()` before making API calls
- Mock data is returned from `demoService.ts`
- All endpoints show as "ready" without health checks

#### Error Handling & Fallback
Structure prediction uses automatic fallback:
```typescript
// If primary model fails, tries next in order
openfold3 → boltz2 → openfold2
boltz2 → openfold3 → openfold2
openfold2 → boltz2 → openfold3
```

## NIM Endpoints

| Service | Port | Purpose | GPU |
|---------|------|---------|-----|
| Qwen3-80B | 8008 | LLM for planning and agent | 2x H200 |
| OpenFold3 | 8000 | Structure prediction (recommended) | H200 |
| Boltz2 | 8001 | Fast structure prediction | B200 |
| OpenFold2 | 8004 | Structure with MSA+template | H200 |
| GenMol | 8005 | De novo molecule generation | RTX 6000 |
| MolMIM | 8006 | Molecule optimization around seed | RTX 6000 |
| DiffDock | 8007 | Molecular docking | B200 |
| MSA Search | 8003 | Multiple sequence alignment | RTX 6000 |
| Evo2-40B | 8002 | DNA/RNA foundation model | 2x H200 |
| ProteinMPNN | 8009 | Sequence design for structures | L40S |
| RFDiffusion | 8010 | De novo protein backbone design | L40S |

## State Management

### Current Approach (App.tsx)
State is managed with 19+ useState hooks in App.tsx:

**UI State:**
- `workflowMode` - 'steps' | 'agent'
- `gatewayUrl` - Backend connection URL
- `currentStepIndex` / `furthestStepIndex` - Navigation
- `selectedDrugId` - Current drug target
- `endpoints` - NIM endpoint health status
- `demoModeEnabled` - Demo mode toggle

**Workflow Data:**
- `proteinInfo` - UniProt data
- `structureResult` - 3D structure prediction
- `generatedMolecules` - Candidate molecules
- `dockingResults` - Docking poses and scores

### Props Flow
Components receive data via props drilling from App.tsx:
```
App.tsx
  └── WorkflowSidebar (gatewayUrl, endpoints, workflowMode, ...)
  └── StructureStep (proteinInfo, gatewayUrl, onStructureResult, ...)
  └── MoleculesStep (selectedDrug, gatewayUrl, onMoleculesGenerated, ...)
```

## Agent Architecture

### Tool Calling Flow
1. User message sent to Qwen3 with system prompt containing tool definitions
2. LLM responds with `<tool_call>{"tool": "...", "arguments": {...}}</tool_call>`
3. `parseToolCall()` extracts the tool call from response
4. `executeTool()` routes to appropriate handler
5. Tool result summarized and fed back to LLM
6. Loop continues until `complete` tool is called

### Available Agent Tools
- `search_uniprot` - Find proteins by name/accession
- `predict_structure` - Call structure prediction APIs
- `generate_molecules` - Create candidate drugs
- `dock_molecules` - Predict binding poses
- `calculate_similarity` - Compare molecules
- `design_protein` - RFDiffusion backbone generation
- `design_sequence` - ProteinMPNN sequence design
- `ask_user` - Request clarification
- `complete` - End workflow with summary
- `execute_raw_request` - Direct API testing

## Key Data Types

### StructurePredictionResult
```typescript
interface StructurePredictionResult {
  structure: string;      // PDB or mmCIF content
  format: 'pdb' | 'cif';
  confidenceScore: number;
  plddt: number;          // Per-residue confidence
  ptm: number;            // Predicted TM-score
  modelUsed: string;
  elapsedTime?: number;
}
```

### DrugTarget
```typescript
interface DrugTarget {
  id: string;
  drugName: string;
  condition: string;
  description: string;
  workflowType: WorkflowType;
  targetProtein: {
    name: string;
    uniprotId: string;
    oligomericState?: string;  // 'monomer' | 'homodimer' | etc.
  };
  referenceSmiles: string;
}
```

## Directory Structure

```
app/
├── docs/                   # Architecture documentation
├── src/
│   ├── components/
│   │   ├── steps/         # Workflow step components
│   │   ├── AgentChat.tsx  # Agent mode interface
│   │   ├── Header.tsx
│   │   └── WorkflowSidebar.tsx
│   ├── data/
│   │   ├── drugs.ts       # Drug target definitions
│   │   ├── endpoints.ts   # NIM endpoint configs
│   │   └── mockData.ts    # Demo mode data
│   ├── hooks/
│   │   └── useProgressTracker.ts
│   ├── services/          # API integrations
│   ├── styles/            # CSS
│   └── types/
│       └── workflow.ts    # TypeScript types
└── vite.config.ts         # Dev server & proxy config
```

## Important Notes

### Homodimer Handling
Some proteins (e.g., COX-2) are homodimers. OpenFold3 handles this via:
```typescript
// Multiple chains with same sequence, different IDs
molecules: [
  { type: 'protein', id: 'A', sequence: '...', msa: {...} },
  { type: 'protein', id: 'B', sequence: '...', msa: {...} }
]
```

### Structure Format
- OpenFold3 and Boltz2 produce PDBx/mmCIF (`.cif`)
- OpenFold2 can produce PDB or mmCIF
- All viewers handle both formats via Mol* library

### MSA (Multiple Sequence Alignment)
- OpenFold3 and OpenFold2 can use MSA for better predictions
- Minimum: single-sequence "MSA" with just the query
- Optional: Full MSA from MSA Search service (port 8003)
