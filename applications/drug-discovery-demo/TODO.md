# Drug Discovery Demo - Improvement Roadmap

> Goal: Demonstrate the superior way of doing biotech/life science workloads on Nebius GPUs with NVIDIA NIMs

## 🔴 CRITICAL - Visual Impact & Core Experience

### 1. Add 2D Molecule Visualization
- [ ] Integrate RDKit.js or SmilesDrawer for SMILES → SVG rendering
- [ ] Show molecular structure grid with hover states
- [ ] Display in MoleculesStep and DockingStep
- **Why**: Users can't evaluate molecules without seeing their structure

### 2. Add Docking Pose Overlay
- [ ] Show ligand poses inside protein binding pocket (3Dmol.js supports this)
- [ ] Color ligand by interaction type (H-bond, hydrophobic, etc.)
- [ ] Side-by-side: protein alone vs protein+ligand
- **Why**: This is the "money shot" of drug discovery demos

### 3. Add Progress Tracking with ETA
- [ ] Show progress bar during structure prediction (can take 2-10 minutes)
- [ ] Display estimated time remaining based on sequence length
- [ ] Show parallel job status indicators
- **Why**: Users abandon demos that appear frozen

### 4. Complete Protein Design UI
- [ ] Test and polish ProteinDesignStep, SequenceDesignStep, ValidationStep
- [ ] Add visual feedback for RFDiffusion generation
- [ ] Show designed backbone before sequence design
- **Why**: Protein design is a major differentiator for Nebius/NIM

### 5. Add Chemical Validation & Drug-Likeness
- [ ] Implement Lipinski's Rule of Five checker
- [ ] Add QED (Quantitative Estimate of Drug-likeness) score
- [ ] Flag PAINS/BRENK problematic scaffolds
- [ ] Show molecular properties: MW, LogP, H-bond donors/acceptors, TPSA
- **Why**: Scientific credibility requires filtering bad molecules

---

## 🟠 HIGH - Professional Polish

### 6. Show GPU Performance Metrics
- [ ] Display inference time per model prominently
- [ ] Show GPU utilization if available from NIM
- [ ] Add comparison: "X times faster than CPU"
- **Why**: This is a Nebius GPU demo - show the speed advantage

### 7. Add Model Comparison Matrix
- [ ] Side-by-side structure predictions from OpenFold3/Boltz2/OpenFold2
- [ ] Show pLDDT, pTM, confidence per model
- [ ] Highlight differences in predicted regions
- **Why**: Demonstrates breadth of NIM options

### 8. Implement Workflow State Persistence
- [ ] Save current workflow to localStorage
- [ ] Add "Resume Previous Session" option
- [ ] Export results as JSON/PDF
- **Why**: Users lose work on page reload

### 9. Add Comprehensive Error Handling
- [ ] Error boundary around each step
- [ ] Retry buttons with exponential backoff
- [ ] Fallback UI when NIM endpoints are down
- [ ] Clear error messages with recovery suggestions
- **Why**: Demo failures kill confidence

### 10. Add pAE (Predicted Aligned Error) Visualization
- [ ] Show contact map / PAE matrix
- [ ] Highlight uncertain regions in structure
- [ ] Add residue-level confidence coloring
- **Why**: pLDDT alone doesn't show domain confidence

---

## 🟡 MEDIUM - Feature Completeness

### 11. Implement GenMol De Novo Generation
- [ ] Add GenMol as alternative to MolMIM
- [ ] Show "generate from scratch" vs "generate analogs" options
- [ ] Display generation diversity metrics
- **Why**: Two molecule generation approaches already deployed

### 12. Add Binding Site Prediction/Highlighting
- [ ] Highlight predicted binding pocket on protein
- [ ] Show pocket volume and druggability score
- [ ] Focus docking visualization on binding site
- **Why**: Context for why docking results matter

### 13. Add Batch Processing UI
- [ ] Upload SMILES file for batch docking
- [ ] Show queue status for multiple jobs
- [ ] Parallel execution with result aggregation
- **Why**: Real use case is screening libraries

### 14. Add Interactive Molecule Editor
- [ ] Simple JSME or Ketcher integration
- [ ] Draw custom molecules for docking
- [ ] Edit generated molecules
- **Why**: Scientists want to tweak candidates

### 15. Add Results Export
- [ ] Export structures as PDB/CIF
- [ ] Export molecules as SMILES/SDF
- [ ] Export full report as PDF
- [ ] Export workflow as reproducible JSON
- **Why**: Users need to take results elsewhere

---

## 🟢 NICE TO HAVE - Polish

### 16. Add Dark Mode
- [ ] Toggle in header
- [ ] Persist preference
- **Why**: Scientists often work at night

### 17. Add Keyboard Shortcuts
- [ ] `N` for next step, `P` for previous
- [ ] `R` to run current prediction
- [ ] `Esc` to cancel
- **Why**: Power user experience

### 18. Add Tutorial/Onboarding
- [ ] First-run walkthrough
- [ ] Highlight key features
- [ ] Link to documentation
- **Why**: New users need guidance

### 19. Add Comparison to Known Drugs
- [ ] For rediscovery targets, show actual drug structure
- [ ] Calculate RMSD to known crystal structure
- [ ] Show "how close did we get?" metrics
- **Why**: Validates the approach scientifically

### 20. Mobile Responsive Design
- [ ] Collapse sidebar on mobile
- [ ] Stack visualizations vertically
- [ ] Touch-friendly controls
- **Why**: Demo at conferences/meetings

---

## 🔵 INFRASTRUCTURE & RELIABILITY

### 21. Add Request Caching
- [ ] Cache structure predictions by sequence hash
- [ ] Cache UniProt lookups
- [ ] Show "using cached result" indicator
- **Why**: Avoid recomputing expensive predictions

### 22. Add Rate Limiting
- [ ] Client-side throttling
- [ ] Queue requests when limit reached
- [ ] Show rate limit status
- **Why**: Don't overload NIM endpoints

### 23. Add Health Check Dashboard
- [ ] Dedicated page showing all endpoint status
- [ ] Response time graphs
- [ ] Model version info
- **Why**: Debugging deployment issues

### 24. Add Request/Response Logging
- [ ] Log API calls for debugging
- [ ] Show request inspector in dev mode
- [ ] Export logs for support
- **Why**: Need visibility into failures

---

## 🟣 SCIENTIFIC CREDIBILITY

### 25. Add Reference Literature Links
- [ ] Link each model to its paper
- [ ] Link drug targets to PubMed/DrugBank
- [ ] Show model accuracy benchmarks
- **Why**: Scientists want to verify claims

### 26. Add Validation Datasets
- [ ] Include known crystal structures for comparison
- [ ] Show benchmark docking results
- [ ] Display expected vs predicted binding affinity
- **Why**: Demonstrates model accuracy

### 27. Add Scientific Disclaimers
- [ ] Caveats for each model type
- [ ] "This is a prediction, not experimental data"
- [ ] Link to limitations documentation
- **Why**: Avoid overpromising

### 28. Add Selectivity Analysis
- [ ] For kinase inhibitors, show off-target predictions
- [ ] Compare docking scores across protein family
- [ ] Highlight selectivity concerns
- **Why**: Real drug discovery cares about selectivity

---

## ⚡ Quick Wins (< 1 day each)

- [ ] Add molecule 2D viewer (SmilesDrawer is <100 lines)
- [ ] Show inference time prominently
- [ ] Add Lipinski filter checkbox
- [ ] Add localStorage persistence for gateway URL
- [ ] Add "Copy SMILES" buttons everywhere
- [ ] Add molecular weight to molecule cards
- [ ] Fix any TypeScript warnings
- [ ] Add loading skeleton states

---

## 📅 Suggested Implementation Order

### Week 1: Visual Impact
- 2D molecules viewer
- Docking pose overlay
- Progress bars with ETA
- Inference timing display

### Week 2: Scientific Credibility
- Drug-likeness filters
- Model comparison view
- Error handling
- pAE visualization

### Week 3: Feature Completeness
- Protein design polish
- GenMol integration
- Batch processing
- Results export

### Week 4: Polish & Testing
- Tutorials/onboarding
- Dark mode
- Mobile responsiveness
- End-to-end testing

---

## Current Strengths ✅

1. Comprehensive NIM coverage (11 models)
2. Two workflow paradigms (Agent + Step-by-Step)
3. Scientific credibility (real drug targets, proper mechanisms)
4. Multiple use cases (small molecules, protein design, enzyme engineering)
5. Clean architecture (components, services, data separation)
6. Streaming LLM support
7. Flexible step system adapts to workflow type
8. Modern TypeScript throughout
9. Custom UI toolkit (no external dependency lock-in)
10. Realistic scientific workflows

---

## Key Metrics to Track

- **Demo completion rate**: % of users who complete a full workflow
- **Time to first prediction**: How quickly users see results
- **Error rate**: % of failed API calls
- **Feature usage**: Which workflows are most popular
- **Performance**: Inference time per model type

---

## 🧬 FINE-TUNING INTEGRATION

### Priority 1: Model Selection (Base vs Fine-Tuned)
- [ ] Add model selector dropdown in Molecules Step
- [ ] Support multiple model variants: Base, Fine-tuned (Kinase, GPCR, etc.), Custom
- [ ] Add badges to indicate model type (Base, Fine-tuned, Custom)
- [ ] Create comparison view: side-by-side results from base vs fine-tuned
- [ ] Add metrics panel showing improvement (QED, docking scores)
- **Why**: Demonstrates fine-tuning value without requiring infrastructure

### Priority 2: Fine-Tuning Job Launcher UI
- [ ] Create FineTuningStep.tsx component
- [ ] Training data selection UI (checkboxes for molecules from current session)
- [ ] Hyperparameter presets (Fast/Balanced/High Quality)
- [ ] Job queue status panel (running jobs, ETA, GPU usage)
- [ ] Model registry (list of user's fine-tuned models)
- [ ] Backend API integration:
  - POST /v1/fine-tuning/jobs
  - GET /v1/fine-tuning/jobs/{id}/status
  - GET /v1/fine-tuning/models
- **Why**: Shows Nebius fine-tuning capabilities end-to-end

### Priority 3: Active Learning Loop
- [ ] Add thumbs up/down feedback buttons per molecule in Molecules Step
- [ ] "Retrain on Feedback" button
- [ ] Generation counter showing iterations
- [ ] Store user feedback for training data
- [ ] Iterative improvement visualization
- **Why**: Most compelling demo of ML lifecycle

### Priority 4: Docking Model Specialization
- [ ] "Optimize Docking Model" option after Structure Step
- [ ] Training data: known ligands + crystallographic poses from PDB
- [ ] Compare base vs specialized DiffDock confidence scores
- [ ] Show improvement metrics (2-3x higher confidence)
- **Why**: Docking is critical for drug discovery

### Priority 5: LLM Domain Fine-Tuning
- [ ] Model selector in AI Planning step
- [ ] Compare outputs: "Base Qwen3" vs "Qwen3-DrugDiscovery"
- [ ] Training data sources: PubMed, patents, research notes
- [ ] Improved research plans with domain-specific knowledge
- **Why**: Shows LLM customization for specialized domains

### Priority 6: Federated Fine-Tuning Showcase
- [ ] "Pharma Consortium Mode" demo scenario
- [ ] Privacy-preserving ML visualization
- [ ] Aggregated model improvements display
- **Why**: Enterprise/pharma differentiator

---

## 📅 Fine-Tuning Implementation Order

### Phase 1: Quick Win
- Model comparison view (base vs pre-fine-tuned)
- Mock fine-tuned models with better results
- Side-by-side metrics display

### Phase 2: Job Management
- Fine-tuning job launcher UI
- Job status tracking
- Model registry

### Phase 3: Active Learning
- Feedback buttons on molecules
- Iterative refinement loop
- Training data management

### Phase 4: Advanced
- Docking specialization
- LLM domain tuning
- Federated learning demo
