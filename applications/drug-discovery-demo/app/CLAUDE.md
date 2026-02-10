# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build Commands

```bash
npm install          # Install dependencies
npm run dev          # Start dev server (http://localhost:5173)
npm run build        # TypeScript check + Vite production build
npm run lint         # ESLint check
npm run preview      # Preview production build
```

## Project Overview

Drug Discovery Demo - Interactive React application showcasing NVIDIA NIMs for AI-driven drug discovery on Nebius AI Cloud. Supports two workflow modes and multiple drug discovery pipelines.

## Architecture

### Two Workflow Modes

1. **Step-by-Step Mode** (`workflowMode: 'steps'`) - Default. Guided linear workflow. Steps vary by workflow type:
   - `small-molecule`: 8 steps (Use Case -> AI Planning -> Sequence -> Structure -> Molecules -> Docking -> Rediscovery -> Summary)
   - `protein-binder`: 8 steps (adds RFDiffusion + ProteinMPNN)
   - `de-novo-protein`: 6 steps (unconditional protein generation)
   - `enzyme-engineering`: 5 steps

2. **Fine-Tuning Mode** (`workflowMode: 'finetuning'`) - Nebius Serverless AI for training custom QSAR models. 6 steps: Data Selection -> Preview -> Config -> Training -> Evaluation -> Screening.

### State Management (React Context)

State is managed via four contexts in `src/contexts/`:

- **GatewayContext** - Connection settings, NIM endpoint health
- **WorkflowContext** - Navigation, selected drug, workflow type, mode switching
- **WorkflowDataContext** - Results flowing between steps (proteinInfo, structureResult, molecules, docking)
- **FineTuningContext** - Dataset, model config, training status, evaluation results

All contexts are combined in `AppProvider.tsx` which wraps the app in `main.tsx`.

### NIM Service Layer

Services in `src/services/` follow these patterns:

**URL Building**: All NIM calls use `buildNimUrl()` from `nimApi.ts`:
- Both dev and prod route through `/api/nim-proxy/{host}/{port}{path}`
- In dev: Vite plugin intercepts and proxies to NIM endpoints
- In prod: Express server proxies to NIM endpoints (supports cluster-internal routing via `NIM_GATEWAY_URL` env var)

**Key endpoints** (defined in `src/data/endpoints.ts`):
| Service | Port | Purpose |
|---------|------|---------|
| Qwen3-80B | 8008 | LLM planning |
| Boltz2 | 8001 | Structure prediction (recommended) |
| OpenFold3 | 8000 | Structure prediction (experimental) |
| DiffDock | 8007 | Molecular docking |
| GenMol | 8005 | Molecule generation |
| RFDiffusion | 8010 | Protein backbone design |
| ProteinMPNN | 8009 | Sequence design |

### Express Server (Production)

The `server/` directory contains a lightweight Express 5 server for production:
- **NIM Proxy** (`server/routes/nimProxy.ts`) - Proxies browser requests to cluster-internal NIM services
- **SPA fallback** - Serves the built React app for all non-API routes
- **Express 5 gotcha**: Wildcard routes use `{*path}` syntax (not `*`). The `{*path}` param returns an **array** of segments.

### K8s Deployment

- `Dockerfile` - Multi-stage build (React frontend + Express server)
- `k8s/deployment.yaml` - Pod spec with `NIM_GATEWAY_URL=nims-gateway` for cluster-internal routing
- `k8s/service.yaml` - LoadBalancer service on port 80
- `deploy.sh` - Build, push, deploy script

## Key Patterns

### OpenFold3 API Format (Critical)

```json
{
  "inputs": [{
    "input_id": "prediction_1",
    "molecules": [
      {"type": "protein", "id": "A", "sequence": "...", "msa": {"main": {"a3m": {"alignment": ">query\n...", "format": "a3m"}}}}
    ],
    "diffusion_samples": 1,
    "output_format": "cif"
  }]
}
```

- `inputs` must be an **array**, not object
- Each molecule needs `msa` with at least query sequence
- For homodimers (e.g., COX-2): add multiple molecules with IDs "A", "B"
- Response: `data.outputs[0].structures_with_scores[0]`

### Homodimer Handling

Check `DrugTarget.targetProtein.oligomericState` - if "homodimer", add multiple chains with same sequence. Use `getNumCopiesFromOligomericState()` helper.

### Structure Prediction Fallback

Primary model fails -> tries next in order: `boltz2 -> openfold3 -> openfold2`

## Testing

Before committing:
- `npm run build` passes (TypeScript + Vite)
- UI flows work in browser
