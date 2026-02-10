# AI Drug Discovery Demo

Interactive demo showcasing NVIDIA NIMs for AI-powered drug discovery and protein design on Nebius AI Cloud.

## Overview

This application provides a dynamic AI agent that can design and execute computational biology workflows using state-of-the-art deep learning models. The agent analyzes your research goal and automatically selects the appropriate tools and models.

## Available Models (NIMs)

| Model | Port | Category | Capability |
|-------|------|----------|------------|
| **Qwen3-80B** | 8008 | LLM | Research planning, analysis, and narration |
| **OpenFold3** | 8000 | Structure | Next-gen protein structure prediction |
| **Boltz2** | 8001 | Structure | Fast protein structure prediction |
| **OpenFold2** | 8004 | Structure | Structure prediction with MSA + templates |
| **GenMol** | 8005 | Molecules | De novo small molecule generation |
| **MolMIM** | 8006 | Molecules | SMILES-guided molecule generation |
| **DiffDock** | 8007 | Docking | Molecular docking pose prediction |
| **ProteinMPNN** | 8009 | Design | Protein sequence design for structures |
| **RFDiffusion** | 8010 | Design | De novo protein structure generation |
| **MSA Search** | 8003 | Utility | Multiple sequence alignment search |
| **Evo2-40B** | 8002 | Utility | DNA/RNA foundation model |

## Realistic Use Cases

### 1. Small Molecule Drug Discovery
**Goal**: Find novel drug candidates that bind to a disease-relevant protein target.

**Workflow**:
1. Identify target protein (UniProt lookup)
2. Predict 3D structure (OpenFold3/Boltz2)
3. Generate candidate molecules (GenMol/MolMIM)
4. Dock molecules to target (DiffDock)
5. Analyze binding poses and scores

**Example targets**: Kinases (cancer), GPCRs (CNS), proteases (antivirals)

---

### 2. De Novo Protein Design
**Goal**: Create entirely new proteins with desired structures or functions.

**Workflow**:
1. Define structural constraints (size, topology, binding site)
2. Generate novel backbone structures (RFDiffusion)
3. Design amino acid sequences (ProteinMPNN)
4. Validate predicted structure (OpenFold3)
5. Iterate if needed

**Applications**: Biosensors, therapeutic proteins, nanomaterials

---

### 3. Protein Binder Design
**Goal**: Design proteins that specifically bind to a target protein.

**Workflow**:
1. Obtain target protein structure (OpenFold3 or PDB)
2. Generate binder scaffolds (RFDiffusion in binder mode)
3. Design binder sequences (ProteinMPNN)
4. Validate binding interface (OpenFold3 complex prediction)

**Applications**: Therapeutic antibody alternatives, diagnostics, research tools

---

### 4. Antiviral Drug Discovery
**Goal**: Find small molecules that inhibit viral proteins.

**Workflow**:
1. Identify viral target (e.g., protease, polymerase, spike)
2. Predict viral protein structure (OpenFold3/Boltz2)
3. Generate antiviral candidates (GenMol)
4. Dock and rank compounds (DiffDock)
5. Analyze for drug-likeness

**Example targets**: SARS-CoV-2 Mpro, HIV protease, Influenza neuraminidase

---

### 5. Enzyme Engineering
**Goal**: Modify enzymes for new substrates, improved stability, or altered activity.

**Workflow**:
1. Obtain enzyme structure (OpenFold3)
2. Identify active site and key residues (Qwen3 analysis)
3. Redesign active site region (RFDiffusion partial diffusion)
4. Optimize sequence (ProteinMPNN)
5. Validate new structure (OpenFold3)

**Applications**: Industrial biocatalysis, biosynthesis, bioremediation

---

### 6. Lead Optimization
**Goal**: Improve properties of existing drug candidates.

**Workflow**:
1. Start with known active compound (seed SMILES)
2. Generate structural analogs (MolMIM)
3. Dock all variants (DiffDock)
4. Compare binding scores and poses
5. Select candidates with improved properties

**Optimization goals**: Potency, selectivity, ADMET properties

---

### 7. Scaffold Hopping
**Goal**: Find new chemical scaffolds with similar biological activity.

**Workflow**:
1. Analyze reference drug structure
2. Generate diverse molecules (GenMol with high diversity)
3. Filter by pharmacophore features (Qwen3)
4. Dock to target (DiffDock)
5. Identify novel scaffolds with good binding

**Use case**: Patent circumvention, improved drug-likeness

---

### 8. Protein Stabilization
**Goal**: Design more stable variants of proteins for therapeutics or research.

**Workflow**:
1. Predict wild-type structure (OpenFold3)
2. Identify instability regions (pLDDT analysis)
3. Redesign unstable regions (RFDiffusion inpainting)
4. Optimize sequences (ProteinMPNN)
5. Validate improved structure (OpenFold3)

**Applications**: Biologics development, vaccine antigens, industrial enzymes

---

### 9. Protein-Protein Interaction (PPI) Modulators
**Goal**: Design molecules that disrupt or stabilize protein-protein interactions.

**Workflow**:
1. Predict complex structure (OpenFold3/Boltz2)
2. Identify interaction hotspots (interface analysis)
3. Generate PPI modulators (GenMol)
4. Dock to interface (DiffDock)
5. Analyze disruption potential

**Applications**: Cancer (p53-MDM2), immune checkpoints, signaling pathways

---

### 10. Antibody-Inspired Therapeutics
**Goal**: Design protein therapeutics that mimic antibody binding.

**Workflow**:
1. Define target epitope on antigen
2. Generate mini-binder scaffolds (RFDiffusion)
3. Design CDR-like loops (ProteinMPNN)
4. Predict complex structure (OpenFold3)
5. Validate binding affinity prediction

**Advantages over antibodies**: Smaller size, easier manufacturing, tissue penetration

---

## Limitations & Caveats

### What This Demo Cannot Do

| Limitation | Explanation |
|------------|-------------|
| **Immunogenicity prediction** | Cannot predict if a protein will trigger immune responses |
| **ADMET prediction** | No absorption, distribution, metabolism, excretion, toxicity models |
| **Experimental validation** | Computational predictions require wet lab validation |
| **Dynamics simulation** | No molecular dynamics for conformational sampling |
| **Allosteric effects** | Limited ability to predict allosteric binding sites |

### Scientific Caveats

- **Structure prediction accuracy**: Even best models have ~1-2Å RMSD errors
- **Docking scoring**: DiffDock confidence ≠ binding affinity
- **Molecule generation**: Generated molecules need synthesis feasibility check
- **Protein design**: Success rate ~10-30% in experimental validation

## Getting Started

### Prerequisites

- Node.js 18+
- Access to Nebius AI Cloud with NIM endpoints deployed
- NIM Gateway URL

### Installation

```bash
cd app
npm install
npm run dev
```

### Configuration

1. Enter your NIM Gateway URL in the sidebar
2. Wait for health checks to verify all services
3. Choose workflow mode:
   - **AI Agent**: Dynamic workflow designed by the AI
   - **Step-by-Step**: Guided workflow with manual control

### Workflow Modes

#### AI Agent Mode (Recommended)
The AI agent analyzes your research goal and automatically:
- Selects appropriate models
- Executes tools in optimal order
- Adapts workflow based on results
- Asks clarifying questions when needed

#### Step-by-Step Mode
Traditional linear workflow:
1. Select drug target
2. Generate research plan
3. Fetch protein sequence
4. Predict structure
5. Generate molecules
6. Dock compounds
7. Analyze results

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      React Frontend                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  Agent Chat  │  │  Step Wizard │  │  3D Viewer   │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Vite Proxy Layer                          │
│              (Development CORS handling)                     │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    NIM Gateway                               │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐          │
│  │ Qwen3   │ │OpenFold3│ │ GenMol  │ │DiffDock │ ...      │
│  │ :8008   │ │  :8000  │ │  :8005  │ │  :8007  │          │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘          │
└─────────────────────────────────────────────────────────────┘
```

## Example Prompts

### Small Molecule Discovery
> "Design a selective inhibitor for BCR-ABL kinase to treat chronic myeloid leukemia. The compound should have good oral bioavailability."

### Protein Design
> "Create a small (100 residue) protein scaffold that can display a peptide epitope for vaccine development."

### Antiviral
> "Find compounds that could inhibit the SARS-CoV-2 main protease (Mpro) to block viral replication."

### Enzyme Engineering
> "Redesign the active site of lipase B to accept larger substrates for industrial biodiesel production."

## Tech Stack

- **Frontend**: React 19, TypeScript, Vite
- **Visualization**: 3Dmol.js, OpenChemLib
- **Styling**: Custom CSS with Nebius design tokens
- **State**: React hooks (no external state library)

## License

Copyright © 2024 Nebius B.V. All rights reserved.
