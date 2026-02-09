# Drug Discovery Demo

Interactive demo application showcasing NVIDIA NIMs for AI-driven drug discovery and protein design workflows on Nebius AI Cloud.

## Overview

This application demonstrates how modern computational biology AI models can be orchestrated to "rediscover" known drugs or design novel proteins. It supports two workflow modes:

- **AI Agent Mode** - Conversational AI agent that dynamically orchestrates discovery based on natural language input
- **Step-by-Step Mode** - Guided linear workflow with explanations at each step

## Quick Start

```bash
npm install
npm run dev
```

Open `http://localhost:5173` and enter your NIM Gateway URL, or enable **Demo Mode** to explore without backend services.

## Two Workflow Modes

### Agent Mode (Dynamic)

A conversational AI agent orchestrates discovery dynamically:

- Describe your drug discovery goal in natural language or select a prepared prompt
- Agent decides which tools to use: `search_uniprot`, `predict_structure`, `generate_molecules`, `dock_molecules`, `calculate_similarity`
- Results panel displays structures, molecules, and docking results in real-time
- Agent can ask clarifying questions and adapts workflow based on intermediate results

**Prepared Prompts:**
- Small Molecule Discovery: "Discover COX-2 inhibitors", "Optimize a lead compound"
- Protein Design: "Design a novel protein", "Design a protein binder"
- Structure Analysis: "Predict protein structure", "Analyze binding site"

### Step-by-Step Mode (Guided)

Linear workflow with four tracks depending on selected target:

#### A. Small Molecule Drug Discovery (8 steps)

1. **Use Case** - Select drug target or enter custom prompt
2. **AI Planning** - Qwen3 generates research plan with target protein identification
3. **Sequence** - Fetch protein from UniProt (optional: Evo2 DNA analysis)
4. **Structure** - Parallel prediction with OpenFold3/Boltz2/OpenFold2
5. **Molecules** - Generate candidates with MolMIM/GenMol
6. **Docking** - DiffDock binding pose prediction
7. **Rediscovery** - Tanimoto similarity analysis vs reference drug
8. **Summary** - Qwen3 generates conference-ready narrative

#### B. Protein Binder Design (8 steps)

Design proteins that bind to a target using RFDiffusion + ProteinMPNN.

#### C. De Novo Protein Design (6 steps)

Create new protein folds from scratch using RFDiffusion unconditional generation.

#### D. Enzyme Engineering (5 steps)

Analyze and characterize enzymes for potential redesign.

## Built-in Drug Targets

| Drug | Target | UniProt | Category | QED |
|------|--------|---------|----------|-----|
| Imatinib | ABL1 tyrosine kinase | P00519 | Kinase Inhibitor | 0.77 |
| Ibuprofen | COX-2 | P35354 | Anti-inflammatory | 0.55 |
| Amoxicillin | PBP2a | P0A0K4 | Antibacterial | 0.60 |
| Metformin | AMPK | Q13131 | Metabolic | 0.47 |
| COVID-19 Mpro | SARS-CoV-2 Protease | P0DTD1 | Antiviral | 0.65 |
| Spike Binder | SARS-CoV-2 RBD | P0DTC2 | Protein Binder | - |
| De Novo Scaffold | Novel Design | - | De Novo Protein | - |
| Lipase Engineering | CALB Lipase | P41365 | Enzyme | - |
| p53-MDM2 Inhibitor | MDM2 | Q00987 | PPI Modulator | 0.72 |
| Dopamine D2 | D2 Receptor | P14416 | GPCR Modulator | 0.58 |
| Custom | User-defined | - | Custom Research | - |

## Required NIMs

### Core Services

| NIM | Port | GPU | Purpose |
|-----|------|-----|---------|
| Qwen3-80B | 8008 | 2x H200 | AI planning, narration, seed generation |
| OpenFold3 | 8000 | 1x H200 | Structure prediction (recommended) |
| Boltz2 | 8001 | 1x B200 | Fast structure prediction |
| OpenFold2 | 8004 | 1x H200 | Structure prediction with MSA |
| GenMol | 8005 | 1x RTX 6000 | De novo molecule generation |
| DiffDock | 8007 | 1x B200 | Molecular docking |

### Optional Services

| NIM | Port | GPU | Purpose |
|-----|------|-----|---------|
| MolMIM | 8006 | 1x RTX 6000 | SMILES-guided molecule generation |
| MSA Search | 8003 | 1x RTX 6000 | Homolog search for better structure prediction |
| Evo2-40B | 8002 | 2x H200 | DNA/RNA foundation model |
| ProteinMPNN | 8009 | 1x L40S | Sequence design for structures |
| RFDiffusion | 8010 | 1x L40S | De novo protein backbone generation |

## API Endpoints

| NIM | Path |
|-----|------|
| Qwen3 | `/v1/chat/completions` |
| OpenFold3 | `/v1/biology/openfold/openfold3/predict` |
| Boltz2 | `/v1/biology/mit/boltz2/predict` |
| OpenFold2 | `/v1/biology/openfold/openfold2/predict-structure-from-msa-and-template` |
| GenMol | `/v1/biology/nvidia/genmol/generate` |
| DiffDock | `/molecular-docking/diffdock/generate` |
| Health | `GET /v1/health/ready` (all services) |

## Demo Mode

Enable **Demo Mode** in the sidebar to explore without GPU infrastructure:

- All endpoints show as "ready"
- Returns mock structure predictions, molecules, and docking results
- Real Tanimoto similarity calculations on mock data
- Useful for UI testing, learning the workflow, and demos without backend

## Key Features

- **Parallel Model Execution** - Structure prediction runs 3 models simultaneously
- **Query Editor** - Edit JSON request bodies for any AI model
- **MSA Enhancement** - Optional sequence alignment for improved accuracy
- **Drug-Likeness Assessment** - Client-side Lipinski rule calculation
- **3D Visualization** - Interactive Mol* protein structure viewer
- **2D Molecule Viewer** - SMILES-based structure drawing
- **PubChem Integration** - Molecule name lookup for context

## Tech Stack

- React 19 + TypeScript + Vite
- Mol* for 3D protein structure visualization
- SMILES Drawer for 2D molecule rendering
- react-markdown for LLM output
- Tanimoto fingerprint similarity (client-side)

## Project Structure

```
src/
  components/
    steps/           # Step-by-step workflow components
    AgentChat.tsx    # Agent mode chat interface
    StructureViewer.tsx
    MoleculeViewer2D.tsx
  services/
    nimApi.ts        # NIM HTTP client
    agent.ts         # Agent orchestration
    agentTools.ts    # Tool definitions
    structurePrediction.ts
    moleculeGeneration.ts
    docking.ts
    similarity.ts
    uniprot.ts
    demoService.ts   # Mock implementations
  data/
    drugs.ts         # Drug target definitions
    endpoints.ts     # NIM configurations
    mockData.ts      # Demo mode data
```

## Scientific Caveats

The demo prominently displays limitations for educational purposes:

- **COX-2**: Obligate homodimer shown as single subunit; heme cofactor excluded
- **COVID-19 Mpro**: Cysteine protease mechanism simplified; covalent modifications not modeled
- **GPCRs**: Transmembrane regions may have lower prediction accuracy
- **p53-MDM2**: Flat hydrophobic interface challenging to target

This is a demonstration tool showcasing AI model capabilities, not actual drug discovery.
