# Drug Discovery Demo - Project Status

Interactive demo showcasing NVIDIA NIM microservices for AI-powered drug rediscovery on Nebius AI Cloud.

## Project Overview

**Goal:** Build a step-by-step workflow that "rediscovers" known drugs (Ibuprofen, Amoxicillin, Metformin) using AI models for structure prediction, molecule generation, and molecular docking.

**Tech Stack:**
- React 19 + TypeScript + Vite 7
- Nebius Brand Guidelines (Deep Blue #050D21, Lime #CDFF64)
- CSS custom properties (no external UI library)

---

## Completed Features

### Core Infrastructure
- [x] Vite + React + TypeScript project setup
- [x] Design tokens based on Nebius Brand Guidelines (`design-tokens.css`)
- [x] Component styling system (`components.css`)
- [x] TypeScript types (`types/workflow.ts`)

### Layout & Navigation
- [x] App shell with header, sidebar, and content area
- [x] Nebius logo SVG component
- [x] Header with connection status indicator
- [x] WorkflowSidebar with step navigation
- [x] Step status indicators (pending/active/completed)
- [x] Click navigation to completed steps
- [x] Back/forward navigation between steps
- [x] Proper step highlighting with visual disabled state for pending steps

### Data Layer
- [x] Drug targets data (`data/drugs.ts`)
  - Ibuprofen (COX-2 target)
  - Amoxicillin (PBP2a target)
  - Metformin (AMPK target)
  - Each includes: mechanism, protein sequence, SMILES, LLM prompt
- [x] NIM endpoints configuration (`data/endpoints.ts`)
  - Qwen3-80B (LLM)
  - OpenFold3, Boltz2, OpenFold2 (Structure)
  - GenMol, MolMIM (Molecules)
  - DiffDock (Docking)
  - MSA Search, Evo2 (Utilities)

### Step 1: Drug Target Selection (UseCaseStep)
- [x] Card grid for drug selection
- [x] Drug details panel (mechanism, target protein, SMILES)
- [x] Selection state management
- [x] Continue button with validation

### Step 2: AI Planning (Placeholder)
- [x] Placeholder UI showing Qwen3 will generate research plan
- [x] Shows LLM prompt preview for selected drug
- [x] Back/Continue navigation

### Step 3: Structure Prediction (StructureStep)
- [x] Target protein info card
- [x] Model selection (OpenFold3/Boltz2/OpenFold2)
- [x] Model badges (Recommended/Fast/Accurate)
- [x] 3D viewer placeholder (Mol* integration pending)
- [x] Processing state with spinner

### Steps 4-7: Placeholders
- [x] Molecule Generation placeholder
- [x] Docking placeholder
- [x] Rediscovery placeholder
- [x] Summary placeholder

### Sidebar Features
- [x] Gateway URL input with debounced health check
- [x] Endpoint health status panel
- [x] Status indicators (unknown/checking/ready/not-ready)
- [x] Organized by category (LLM, Structure, Molecules, Docking, Utility)

---

## TODO - Remaining Work

### High Priority

#### API Integration
- [ ] Real health check calls to NIM endpoints
- [ ] Structure prediction API call (OpenFold3/Boltz2/OpenFold2)
- [ ] Molecule generation API call (GenMol)
- [ ] DiffDock docking API call
- [ ] Qwen3 LLM integration for planning/narration

#### 3D Visualization
- [ ] Integrate Mol* viewer for protein structures
- [ ] Display predicted PDB structures
- [ ] Interactive rotation/zoom controls

#### Step 2: AI Planning (Full Implementation)
- [ ] Qwen3 API integration
- [ ] Streaming response display
- [ ] Research plan formatting
- [ ] Loading/error states

#### Step 4: Molecule Generation (Full Implementation)
- [ ] GenMol API integration
- [ ] Generate 100+ candidate molecules
- [ ] Display generated SMILES list
- [ ] Molecule preview/gallery

#### Step 5: Docking (Full Implementation)
- [ ] DiffDock API integration
- [ ] Batch docking of generated molecules
- [ ] Binding pose visualization
- [ ] Docking score table/ranking

#### Step 6: Rediscovery (Full Implementation)
- [ ] Tanimoto similarity calculation
- [ ] Morgan fingerprint comparison
- [ ] Similarity score display
- [ ] Match highlighting for reference drug

#### Step 7: Summary (Full Implementation)
- [ ] Qwen3 summary generation
- [ ] Top candidates display
- [ ] Scientific interpretation
- [ ] Export/download results

### Medium Priority

#### UX Improvements
- [ ] Error handling and error states
- [ ] Loading skeletons
- [ ] Toast notifications
- [ ] Keyboard navigation improvements
- [ ] Mobile responsive layout

#### Data Persistence
- [ ] Save/load workflow state
- [ ] LocalStorage for gateway URL
- [ ] Session persistence

#### Performance
- [ ] API response caching
- [ ] Lazy loading for heavy components
- [ ] Optimistic UI updates

### Low Priority

#### Additional Features
- [ ] Dark mode support
- [ ] Export results as PDF/JSON
- [ ] Share workflow via URL
- [ ] Comparison mode for multiple drugs
- [ ] Custom drug target input

#### Polish
- [ ] Animations and transitions
- [ ] Accessibility audit (ARIA, screen readers)
- [ ] Unit tests
- [ ] E2E tests

---

## File Structure

```
applications/drug-discovery-demo-claude/
├── Nebius Brand Guidelines.pdf
├── STATUS.md                    # This file
└── app/
    ├── package.json
    ├── tsconfig.json
    ├── vite.config.ts
    └── src/
        ├── main.tsx             # Entry point
        ├── App.tsx              # Main app + state management
        ├── types/
        │   └── workflow.ts      # TypeScript interfaces
        ├── data/
        │   ├── drugs.ts         # Drug targets data
        │   └── endpoints.ts     # NIM endpoint configs
        ├── styles/
        │   ├── design-tokens.css # Colors, spacing, typography
        │   └── components.css    # All component styles
        └── components/
            ├── Header.tsx
            ├── NebiusLogo.tsx
            ├── WorkflowSidebar.tsx
            └── steps/
                ├── UseCaseStep.tsx      # Drug selection (complete)
                ├── StructureStep.tsx    # Structure prediction (UI complete)
                └── PlaceholderStep.tsx  # Generic placeholder
```

---

## Running the App

```bash
cd applications/drug-discovery-demo-claude/app
npm install
npm run dev
```

Dev server runs at http://localhost:5177/

---

## Architecture Notes

### State Management
- All state managed in `App.tsx` using React hooks
- `currentStepIndex` tracks current step
- `furthestStepIndex` tracks progress for navigation
- Step statuses derived from indices (not stored individually)

### Navigation Logic
- Steps before current = completed (green)
- Current step = active (blue)
- Steps after furthest = pending (grayed out, not clickable)
- Can click any step up to furthest reached

### Styling Approach
- CSS custom properties for theming
- Single component stylesheet
- Class-based status styling (`.active`, `.completed`, `.pending`)
- Nebius brand colors throughout
