# NIMs Drug Discovery Demo — Plan

## Objective
Build a polished, conference-ready demo that walks a user through an industry-style drug discovery workflow. The UI connects directly to NIM endpoints via a LoadBalancer, performs health checks, chains results between steps automatically, and "rediscovers" known drugs among AI-generated candidates.

## Target Drugs for Rediscovery

### 1. Ibuprofen (Analgesic / Anti-inflammatory)
- **Mechanism**: Blocks COX-1 and COX-2 enzymes → reduces prostaglandins → lowers pain, inflammation, fever
- **Target Protein**: COX-2 (Prostaglandin-endoperoxide synthase 2) — UniProt P35354
- **Reference SMILES**: `CC(C)Cc1ccc(cc1)C(C)C(=O)O`
- **LLM Prompt**: "Design a small-molecule therapeutic that selectively inhibits cyclooxygenase enzymes responsible for converting arachidonic acid into pro-inflammatory prostaglandins. The compound should reduce peripheral and central sensitization to nociceptive stimuli, suppress inflammation-associated vasodilation and edema, and lower hypothalamic temperature set-points responsible for fever. The agent must act reversibly, demonstrate dose-dependent efficacy, and preserve normal cellular signaling pathways not involved in inflammatory mediator synthesis."

### 2. Amoxicillin (Antibacterial)
- **Mechanism**: Interferes with bacterial cell wall formation → bacteria burst and die
- **Target Protein**: PBP (Penicillin-binding proteins) — bacterial transpeptidases
- **Reference SMILES**: `CC1(C(N2C(S1)C(C2=O)NC(=O)C(C3=CC=C(C=C3)O)N)C(=O)O)C`
- **LLM Prompt**: "Develop a bactericidal compound that selectively targets prokaryotic cell wall biosynthesis by binding enzymes involved in peptidoglycan cross-linking. The agent should destabilize bacterial structural integrity during replication, leading to osmotic lysis, while exhibiting minimal affinity for eukaryotic cellular components. Activity should be limited to bacterial organisms and ineffective against viral or host cellular processes."

### 3. Metformin (Metabolic Regulation)
- **Mechanism**: Decreases hepatic glucose production, increases insulin sensitivity, slows glucose absorption
- **Target Protein**: AMPK pathway / mitochondrial complex I
- **Reference SMILES**: `CN(C)C(=N)NC(=N)N`
- **LLM Prompt**: "Create a metabolic modulator that lowers systemic glucose concentrations by suppressing hepatic gluconeogenesis, enhancing peripheral insulin sensitivity, and reducing intestinal glucose uptake. The compound should not stimulate insulin secretion directly, must function independently of pancreatic beta-cell activity, and should improve glycemic control through long-term modulation of energy metabolism pathways."

---

## Scope (Current)
- UI calls NIM endpoints directly via LoadBalancer (no backend proxy)
- NGC key auth handled in infrastructure (not in demo UI)
- Qwen3 as workflow copilot for planning and narration
- Hardcoded target protein sequences (to be improved later)
- Hardcoded reference drug SMILES for similarity comparison

---

## NIM Endpoints

### LLM
| Model | Path | Purpose |
|-------|------|---------|
| Qwen3 | `POST /v1/chat/completions` | Research planning, narration, summary |

### Structure Prediction
| Model | Path | Purpose |
|-------|------|---------|
| AlphaFold2 | `POST /v1/biology/deepmind/alphafold2` | Protein structure (monomer) |
| ESMFold | `POST /v1/biology/nvidia/esmfold` | Fast structure prediction (no MSA) |
| OpenFold2 | `POST /v1/biology/openfold/openfold2/predict-structure-from-msa-and-template` | Structure with MSA+template |
| OpenFold3 | `POST /v1/biology/openfold/openfold3/predict` | Next-gen structure prediction |
| Boltz2 | `POST /v1/biology/mit/boltz2/predict` | Alternative structure model |

### Molecule Generation
| Model | Path | Purpose |
|-------|------|---------|
| GenMol | `POST /v1/biology/nvidia/genmol/generate` | Generate candidate molecules |
| MolMIM | `POST /v1/biology/nvidia/molmim/generate` | Generate molecules around input SMILES |

### Docking & Validation
| Model | Path | Purpose |
|-------|------|---------|
| DiffDock | `POST /v1/biology/mit/diffdock` | Dock molecules to protein, score binding |

### Utilities
| Model | Path | Purpose |
|-------|------|---------|
| ESM2-650m | `POST /v1/biology/meta/esm2-650m` | Protein embeddings |
| MSA-Search | `POST /v1/biology/colabfold/msa-search/predict` | Multiple sequence alignment |
| ProteinMPNN | `POST /v1/biology/ipd/proteinmpnn/predict` | Inverse folding (sequence design) |

### Health Checks
- `GET /v1/health/ready`
- `GET /v1/health/live`

---

## Workflow (Chained Steps)

```
┌─────────────────────────────────────────────────────────────────┐
│  1. USE CASE SELECTION                                          │
│     User picks: Ibuprofen | Amoxicillin | Metformin             │
│     → Loads target protein sequence + LLM prompt + ref SMILES   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  2. HEALTH CHECK                                                │
│     Verify all required NIMs are ready                          │
│     → Qwen3, Structure model, GenMol, DiffDock                  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  3. AI PLANNING (Qwen3)                                         │
│     Input: Detailed prompt for selected drug class              │
│     Output: Research plan + scientific context                  │
│     → Stored for narration throughout workflow                  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  4. STRUCTURE PREDICTION (AlphaFold2 / ESMFold)                 │
│     Input: Target protein sequence (COX-2, PBP, or metabolic)   │
│     Output: PDB structure file                                  │
│     → Rendered in Mol* 3D viewer                                │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  5. MOLECULE GENERATION (GenMol / MolMIM)                       │
│     Input: Target context from planning step                    │
│     Output: 100+ candidate SMILES                               │
│     → Displayed as 2D molecule grid                             │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  6. DOCKING (DiffDock)                                          │
│     Input: PDB structure + top candidate SMILES                 │
│     Output: Binding poses + docking scores                      │
│     → Visualize docked poses in Mol*                            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  7. REDISCOVERY SCORING                                         │
│     Compare generated molecules to reference drug               │
│     Method: Tanimoto similarity (Morgan fingerprints)           │
│     → Highlight matches, rank by similarity                     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  8. SUMMARY (Qwen3)                                             │
│     Input: All workflow outputs                                 │
│     Output: Plain-language summary for non-experts              │
│     → Key findings, top candidates, next steps                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Data Assets

### Hardcoded Protein Sequences
```
COX-2 (Human): [UniProt P35354 - to be added]
PBP (S. aureus): [UniProt Q6GIK7 or similar - to be added]
AMPK: [UniProt Q13131 - to be added]
```

### Reference Drug SMILES
```
Ibuprofen:   CC(C)Cc1ccc(cc1)C(C)C(=O)O
Amoxicillin: CC1(C(N2C(S1)C(C2=O)NC(=O)C(C3=CC=C(C=C3)O)N)C(=O)O)C
Metformin:   CN(C)C(=N)NC(=N)N
```

---

## UI Requirements
- Single page with guided flow and clear step descriptions
- LoadBalancer URL configurable in sidebar
- Each step shows: description, input preview, run button, output display
- "Happy path" is one-click per step (or auto-advance option)
- Mol* 3D viewer for protein structures and docking poses
- 2D molecule grid for generated candidates
- Rediscovery panel with similarity scores and highlighting
- Results persist and auto-feed into next step

---

## Tech Stack
- React + TypeScript + Vite
- Nebius brand design system (Deep Blue, Lime, Inter, Gramatika)
- Mol* (molstar) for 3D visualization
- RDKit.js or similar for 2D molecule rendering and fingerprints
- Client-side Tanimoto similarity calculation

---

## Deployment Plan (Later)
- Containerize frontend (nginx + static build)
- Deploy to same K8s cluster/namespace as NIMs
- Configure ingress/service per best practices

---

## Future Enhancements
- Parallel structure model comparison (AlphaFold2 vs ESMFold vs OpenFold)
- ADMET/PK predictions for candidate filtering
- Larger curated compound database (ChEMBL, DrugBank subsets)
- Chat-based interaction with Qwen3 for exploratory queries
- Export results as PDF report
