# Drug Discovery Demo

Interactive demo application showcasing NVIDIA NIMs for AI-driven drug discovery workflows on Nebius AI Cloud.

## Quick Start

```bash
npm install
npm run dev
```

Open `http://localhost:5173` and enter your NIM LoadBalancer URL.

## Required NIMs

### Core Services

| NIM | Port | GPU | Purpose |
|-----|------|-----|---------|
| Qwen3-80B | 8008 | 2× H200 | AI planning & summarization |
| OpenFold3 | 8000 | 1× H200 | Structure prediction |
| Boltz2 | 8001 | 1× B200 | Fast structure prediction |
| OpenFold2 | 8004 | 1× H200 | Structure prediction (MSA) |
| GenMol | 8005 | 1× RTX 6000 | Molecule generation |
| DiffDock | 8007 | 1× B200 | Molecular docking |

### Optional Services

| NIM | Port | GPU | Purpose |
|-----|------|-----|---------|
| MolMIM | 8006 | 1× RTX 6000 | SMILES-guided generation |
| MSA Search | 8003 | 1× RTX 6000 | Sequence alignment |
| Evo2-40B | 8002 | 2× H200 | DNA/RNA foundation model |

## Workflow

1. **Select Target** - Choose drug discovery goal (Ibuprofen, Amoxicillin, Metformin, or custom)
2. **AI Planning** - Qwen3 generates research plan and identifies target protein (UniProt ID)
3. **Get Sequence** - Fetch protein sequence from UniProt
4. **Structure Prediction** - OpenFold3/Boltz2/OpenFold2 predicts 3D structure (Mol* viewer)
5. **Molecule Generation** - GenMol generates candidate molecules with QED scores
6. **Docking** - DiffDock predicts binding poses and confidence scores
7. **Rediscovery** - Tanimoto similarity analysis against reference drug
8. **Summary** - Qwen3 generates conference-ready results narrative

## Built-in Drug Targets

| Drug | Target | UniProt | QED |
|------|--------|---------|-----|
| Ibuprofen | COX-2 | P35354 | 0.55 |
| Amoxicillin | PBP2 | P0A0K4 | 0.60 |
| Metformin | AMPK | Q13131 | 0.47 |

## API Endpoints

| NIM | Path |
|-----|------|
| Qwen3 | `/v1/chat/completions` |
| OpenFold3 | `/v1/biology/openfold/openfold3/predict` |
| Boltz2 | `/v1/biology/mit/boltz2/predict` |
| OpenFold2 | `/v1/biology/openfold/openfold2/predict-structure-from-msa-and-template` |
| GenMol | `/v1/biology/nvidia/genmol/generate` |
| DiffDock | `/molecular-docking/diffdock/generate` |

Health checks: `GET /v1/health/ready`

## Tech Stack

- React 19 + TypeScript + Vite
- Mol* for 3D structure visualization
- react-markdown for LLM output rendering
- Tanimoto fingerprint similarity (client-side)
