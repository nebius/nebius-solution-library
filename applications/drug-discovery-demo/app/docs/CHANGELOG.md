# Drug Discovery Demo - Changelog

## [Unreleased] - 2026-02-09

### Major Features

#### Nebius Serverless Fine-Tuning Mode
A complete new workflow mode for training custom QSAR models using Nebius Serverless AI.

**New Components:**
- `src/components/finetuning/FineTuningMode.tsx` - Main container component
- `src/components/finetuning/FineTuningSidebar.tsx` - Sidebar with Nebius branding
- `src/components/finetuning/steps/DataSelectionStep.tsx` - ChEMBL search, CSV upload, demo datasets
- `src/components/finetuning/steps/DataPreviewStep.tsx` - Dataset statistics and validation
- `src/components/finetuning/steps/ModelConfigStep.tsx` - Model and hyperparameter configuration
- `src/components/finetuning/steps/TrainingStep.tsx` - Live training progress with GPU status
- `src/components/finetuning/steps/EvaluationStep.tsx` - Model performance metrics
- `src/components/finetuning/steps/ScreeningStep.tsx` - Model deployment and compound screening
- `src/components/finetuning/index.ts` - Module exports

**New Services:**
- `src/services/nebiusServerless.ts` - Nebius Serverless API client
  - Training job management
  - Endpoint deployment
  - Demo mode simulation with realistic progress
  - Cost tracking ($6/hr for H200 GPU)
- `src/services/chemblApi.ts` - ChEMBL database integration
  - Target search
  - Activity data fetching
  - Demo datasets (COX-2, ABL1, Dopamine D2)

**New State Management:**
- `src/contexts/FineTuningContext.tsx` - Complete state for fine-tuning workflow
  - Navigation (6 steps)
  - Dataset selection and validation
  - Model configuration
  - Training job tracking
  - Evaluation results
  - Endpoint deployment

**New Types:**
- `src/types/finetuning.ts` - TypeScript definitions
  - DatasetInfo, TrainingConfig, TrainingStatus
  - EvaluationResult, EndpointInfo, ScreeningResult
  - BaseModelId, JobState, HyperParameters

**New Styles:**
- `src/styles/features/finetuning.css` - ~900 lines of CSS
  - Serverless branding styles
  - Data selection cards
  - Training progress visualization
  - Metrics cards and charts
  - Results tables

**Modified Files:**
- `src/contexts/WorkflowContext.tsx` - Added 'finetuning' to WorkflowMode type
- `src/contexts/AppProvider.tsx` - Added FineTuningProvider wrapper
- `src/App.tsx` - Added rendering for finetuning mode
- `src/components/WorkflowSidebar.tsx` - Added Fine-Tuning mode button
- `src/styles/index.css` - Added finetuning.css import

#### Architecture Refactoring (from previous sessions)

**React Context Migration:**
- `src/contexts/GatewayContext.tsx` - Connection settings, demo mode, endpoints
- `src/contexts/WorkflowContext.tsx` - Navigation, selected drug, workflow type
- `src/contexts/WorkflowDataContext.tsx` - Results flowing between steps
- `src/contexts/AppProvider.tsx` - Combined provider component

**Hooks:**
- `src/hooks/useAsyncOperation.ts` - Common async operation pattern
- `src/hooks/useSelectionToggle.ts` - Selection toggle logic
- `src/hooks/index.ts` - Module exports

**Utilities:**
- `src/utils/formatting.ts` - Formatting helpers

**CSS Modularization:**
- `src/styles/base.css` - Foundation styles
- `src/styles/components/sidebar.css` - Sidebar styles
- `src/styles/components/buttons.css` - Button styles
- `src/styles/components/cards.css` - Card styles
- `src/styles/components/forms.css` - Form styles
- `src/styles/features/agent-chat.css` - Agent chat styles
- `src/styles/index.css` - Central import file

**Documentation:**
- `docs/ARCHITECTURE.md` - System architecture
- `docs/SETUP.md` - Developer setup guide
- `docs/SERVERLESS_FINETUNING.md` - Fine-tuning design document
- `CLAUDE.md` - Claude Code configuration with custom agents

### Other Improvements

- Added K8s scaling panel (`src/components/K8sScalingPanel.tsx`)
- Added DrugLikenessPanel (`src/components/DrugLikenessPanel.tsx`)
- Added MoleculeViewer2D (`src/components/MoleculeViewer2D.tsx`)
- Added StepAssistant (`src/components/StepAssistant.tsx`)
- Added AgentChat (`src/components/AgentChat.tsx`)
- Added ProteinDesignStep for de novo protein design
- Added SequenceDesignStep for ProteinMPNN integration
- Added ValidationStep for structure validation
- Added response parsers (`src/services/responseParsers.ts`)
- Added demo service (`src/services/demoService.ts`)
- Added drug likeness calculations (`src/services/drugLikeness.ts`)
- Added K8s service (`src/services/k8sService.ts`)
- Added agent services (`src/services/agent.ts`, `src/services/agentTools.ts`)
- Added K8s mapping data (`src/data/k8sMapping.ts`)
- Added mock data (`src/data/mockData.ts`)
- Added vite kubectl plugin (`vite-plugin-kubectl.ts`)

### Technical Details

**Fine-Tuning Workflow Steps:**
1. **Data Selection** - Three data sources:
   - ChEMBL database search (COX-2, ABL1, etc.)
   - CSV file upload (smiles,activity format)
   - Demo datasets (pre-loaded)

2. **Data Preview** - Validation and statistics:
   - Compound count and activity range
   - Activity distribution histogram
   - Train/Validation/Test split (80/10/10)

3. **Model Config** - Base model and hyperparameters:
   - ChemBERTa-77M-MTR (recommended)
   - ChemBERTa-77M-MLM
   - MolBERT-100M
   - Configurable: epochs, batch size, learning rate, etc.

4. **Training** - Nebius Serverless GPU:
   - Platform: gpu-h200-sxm
   - Preset: 1gpu-16vcpu-200gb
   - Live progress with metrics
   - Cost tracking ($6/hr)

5. **Evaluation** - Model performance:
   - R², MAE, RMSE metrics
   - Predicted vs Actual scatter plot
   - Baseline comparison

6. **Screening** - Deployment and inference:
   - One-click deployment to serverless endpoint
   - Compound screening with SMILES input
   - Results export (CSV)

**Demo Mode:**
- Simulates complete training workflow
- Realistic progress curves
- Generated evaluation metrics
- Works without Nebius connection
