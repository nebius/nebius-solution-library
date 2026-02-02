import { useState, useCallback, useEffect, useRef, useMemo } from 'react';
import { Header } from './components/Header';
import { WorkflowSidebar } from './components/WorkflowSidebar';
import { UseCaseStep } from './components/steps/UseCaseStep';
import { AIPlanningStep } from './components/steps/AIPlanningStep';
import { SequenceStep } from './components/steps/SequenceStep';
import { StructureStep } from './components/steps/StructureStep';
import { MoleculesStep } from './components/steps/MoleculesStep';
import { DockingStep } from './components/steps/DockingStep';
import { RediscoveryStep } from './components/steps/RediscoveryStep';
import { SummaryStep } from './components/steps/SummaryStep';
import { DRUG_TARGETS, getDrugById } from './data/drugs';
import { NIM_ENDPOINTS } from './data/endpoints';
import { checkAllEndpointsHealth } from './services/nimApi';
import type { StructurePredictionResult } from './services/structurePrediction';
import type { GeneratedMolecule } from './services/moleculeGeneration';
import type { DockingResult } from './services/docking';
import type { WorkflowStep, WorkflowStepId } from './types/workflow';
import type { NimEndpoint } from './data/endpoints';

import './styles/design-tokens.css';
import './styles/components.css';

// Step definitions (static)
const WORKFLOW_STEPS: { id: WorkflowStepId; title: string; subtitle: string }[] = [
  { id: 'use-case', title: 'Drug Target', subtitle: 'Select drug to rediscover' },
  { id: 'ai-planning', title: 'AI Planning', subtitle: 'Qwen3 research plan' },
  { id: 'sequence', title: 'Sequence', subtitle: 'Fetch from UniProt' },
  { id: 'structure', title: 'Structure', subtitle: 'Predict target protein' },
  { id: 'molecules', title: 'Molecules', subtitle: 'Generate candidates' },
  { id: 'docking', title: 'Docking', subtitle: 'DiffDock validation' },
  { id: 'rediscovery', title: 'Rediscovery', subtitle: 'Score similarity' },
  { id: 'summary', title: 'Summary', subtitle: 'Results & insights' },
];

// Protein info from UniProt
interface ProteinInfo {
  accession: string;
  name: string;
  organism: string;
  sequence: string;
  length: number;
}

function App() {
  // State
  const [gatewayUrl, setGatewayUrl] = useState('');
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [furthestStepIndex, setFurthestStepIndex] = useState(0);
  const [selectedDrugId, setSelectedDrugId] = useState<string | null>(null);
  const [customPrompt, setCustomPrompt] = useState('');
  const [selectedStructureModel, setSelectedStructureModel] = useState<string | null>(null);
  const [endpoints, setEndpoints] = useState<NimEndpoint[]>(NIM_ENDPOINTS);
  const [isCheckingHealth, setIsCheckingHealth] = useState(false);

  // Workflow data (flows between steps)
  const [researchPlan, setResearchPlan] = useState('');
  const [identifiedUniprotId, setIdentifiedUniprotId] = useState('');
  const [proteinInfo, setProteinInfo] = useState<ProteinInfo | null>(null);
  const [structureResult, setStructureResult] = useState<StructurePredictionResult | null>(null);
  const [generatedMolecules, setGeneratedMolecules] = useState<GeneratedMolecule[]>([]);
  const [dockingResults, setDockingResults] = useState<DockingResult[]>([]);

  // Ref for debounce timer
  const healthCheckTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Derived: current step ID
  const currentStepId = WORKFLOW_STEPS[currentStepIndex].id;

  // Derived: steps with status (computed from indices)
  const steps: WorkflowStep[] = useMemo(() => {
    return WORKFLOW_STEPS.map((step, index) => {
      let status: WorkflowStep['status'];
      if (index === currentStepIndex) {
        status = 'active';
      } else if (index < currentStepIndex || index <= furthestStepIndex) {
        status = 'completed';
      } else {
        status = 'pending';
      }
      return { ...step, status };
    });
  }, [currentStepIndex, furthestStepIndex]);

  // Get selected drug details
  const selectedDrug = selectedDrugId ? getDrugById(selectedDrugId) ?? null : null;

  // Computed
  const requiredEndpoints = endpoints.filter((e) => e.required);
  const isConnected = requiredEndpoints.some((e) => e.status === 'ready');

  // Health check function (reusable)
  const runHealthCheck = useCallback(async () => {
    if (!gatewayUrl.trim()) return;

    setIsCheckingHealth(true);
    setEndpoints((prev) =>
      prev.map((e) => ({ ...e, status: 'checking' as const }))
    );

    // Check all endpoints in parallel using the API service
    const results = await checkAllEndpointsHealth(gatewayUrl, NIM_ENDPOINTS);

    setEndpoints((prev) =>
      prev.map((endpoint) => {
        const result = results.find((r) => r.id === endpoint.id);
        return result ? { ...endpoint, status: result.status } : endpoint;
      })
    );
    setIsCheckingHealth(false);
  }, [gatewayUrl]);

  // Run health check when gateway URL changes (debounced)
  useEffect(() => {
    if (healthCheckTimerRef.current) {
      clearTimeout(healthCheckTimerRef.current);
    }

    if (!gatewayUrl.trim()) {
      setEndpoints((prev) =>
        prev.map((e) => ({ ...e, status: 'unknown' as const }))
      );
      return;
    }

    healthCheckTimerRef.current = setTimeout(runHealthCheck, 800);

    return () => {
      if (healthCheckTimerRef.current) {
        clearTimeout(healthCheckTimerRef.current);
      }
    };
  }, [gatewayUrl, runHealthCheck]);

  // Navigation handlers
  const goToStep = useCallback((stepId: WorkflowStepId) => {
    const index = WORKFLOW_STEPS.findIndex((s) => s.id === stepId);
    if (index !== -1) {
      setCurrentStepIndex(index);
    }
  }, []);

  const goToNextStep = useCallback(() => {
    const nextIndex = currentStepIndex + 1;
    if (nextIndex < WORKFLOW_STEPS.length) {
      setCurrentStepIndex(nextIndex);
      setFurthestStepIndex((prev) => Math.max(prev, nextIndex));
    }
  }, [currentStepIndex]);

  const goToPrevStep = useCallback(() => {
    if (currentStepIndex > 0) {
      setCurrentStepIndex(currentStepIndex - 1);
    }
  }, [currentStepIndex]);

  const handleStepClick = useCallback(
    (stepId: WorkflowStepId) => {
      const clickedIndex = WORKFLOW_STEPS.findIndex((s) => s.id === stepId);
      // Allow clicking on any step up to the furthest reached
      if (clickedIndex <= furthestStepIndex) {
        goToStep(stepId);
      }
    },
    [furthestStepIndex, goToStep]
  );

  // Handle drug selection - reset all workflow state when changing drugs
  const handleSelectDrug = useCallback((drugId: string | null) => {
    // Only reset if actually changing to a different drug
    if (drugId !== selectedDrugId) {
      // Reset all workflow data
      setResearchPlan('');
      setIdentifiedUniprotId('');
      setProteinInfo(null);
      setStructureResult(null);
      setGeneratedMolecules([]);
      setDockingResults([]);
      setSelectedStructureModel(null);
      // Reset progress (but stay on step 1)
      setFurthestStepIndex(0);
    }
    setSelectedDrugId(drugId);
  }, [selectedDrugId]);

  // Render step content
  const renderStepContent = () => {
    switch (currentStepId) {
      case 'use-case':
        return (
          <UseCaseStep
            drugs={DRUG_TARGETS}
            selectedDrugId={selectedDrugId}
            customPrompt={customPrompt}
            onSelectDrug={handleSelectDrug}
            onCustomPromptChange={setCustomPrompt}
            onContinue={goToNextStep}
          />
        );

      case 'ai-planning':
        return (
          <AIPlanningStep
            selectedDrug={selectedDrug}
            customPrompt={customPrompt}
            gatewayUrl={gatewayUrl}
            savedPlan={researchPlan}
            savedUniprotId={identifiedUniprotId}
            onPlanChange={(plan: string, uniprotId: string) => {
              setResearchPlan(plan);
              setIdentifiedUniprotId(uniprotId);
            }}
            onBack={goToPrevStep}
            onContinue={(plan: string, uniprotId: string) => {
              setResearchPlan(plan);
              setIdentifiedUniprotId(uniprotId);
              goToNextStep();
            }}
          />
        );

      case 'sequence':
        return (
          <SequenceStep
            uniprotId={identifiedUniprotId}
            onUniprotIdChange={setIdentifiedUniprotId}
            proteinInfo={proteinInfo}
            onProteinInfoChange={setProteinInfo}
            gatewayUrl={gatewayUrl}
            onBack={goToPrevStep}
            onContinue={goToNextStep}
          />
        );

      case 'structure':
        return (
          <StructureStep
            proteinInfo={proteinInfo}
            gatewayUrl={gatewayUrl}
            selectedModel={selectedStructureModel}
            onSelectModel={setSelectedStructureModel}
            onStructureResult={setStructureResult}
            onContinue={goToNextStep}
            onBack={goToPrevStep}
          />
        );

      case 'molecules':
        return (
          <MoleculesStep
            selectedDrug={selectedDrug}
            gatewayUrl={gatewayUrl}
            onMoleculesGenerated={setGeneratedMolecules}
            onContinue={goToNextStep}
            onBack={goToPrevStep}
          />
        );

      case 'docking':
        return (
          <DockingStep
            structureResult={structureResult}
            generatedMolecules={generatedMolecules}
            selectedDrug={selectedDrug}
            gatewayUrl={gatewayUrl}
            onDockingResults={setDockingResults}
            onContinue={goToNextStep}
            onBack={goToPrevStep}
          />
        );

      case 'rediscovery':
        return (
          <RediscoveryStep
            selectedDrug={selectedDrug}
            dockingResults={dockingResults}
            onContinue={goToNextStep}
            onBack={goToPrevStep}
          />
        );

      case 'summary':
        return (
          <SummaryStep
            selectedDrug={selectedDrug}
            proteinInfo={proteinInfo}
            structureResult={structureResult}
            generatedMolecules={generatedMolecules}
            dockingResults={dockingResults}
            gatewayUrl={gatewayUrl}
            onBack={goToPrevStep}
            onRestart={() => {
              setCurrentStepIndex(0);
              setFurthestStepIndex(0);
              setSelectedDrugId(null);
              setCustomPrompt('');
              setIdentifiedUniprotId('');
              setProteinInfo(null);
              setStructureResult(null);
              setGeneratedMolecules([]);
              setDockingResults([]);
            }}
          />
        );

      default:
        return null;
    }
  };

  return (
    <div className="app-layout">
      <div className="bg-pattern" />
      <Header isConnected={isConnected} />

      <main className="app-main">
        <WorkflowSidebar
          steps={steps}
          onStepClick={handleStepClick}
          gatewayUrl={gatewayUrl}
          onGatewayUrlChange={setGatewayUrl}
          endpoints={endpoints}
          isCheckingHealth={isCheckingHealth}
          onReconnect={runHealthCheck}
        />

        <div className="content">{renderStepContent()}</div>
      </main>
    </div>
  );
}

export default App;
