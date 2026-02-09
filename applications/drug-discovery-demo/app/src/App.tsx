/**
 * App.tsx - Main Application Component
 *
 * This is the root component that manages the entire drug discovery workflow.
 * State is now managed via React Context (see contexts/ directory):
 * - GatewayContext: Connection settings, demo mode, endpoints
 * - WorkflowContext: Navigation, selected drug, workflow type
 * - WorkflowDataContext: Results flowing between steps
 *
 * @see docs/ARCHITECTURE.md for detailed documentation
 */

import { useCallback } from 'react';
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
import { ProteinDesignStep } from './components/steps/ProteinDesignStep';
import { SequenceDesignStep } from './components/steps/SequenceDesignStep';
import { ValidationStep } from './components/steps/ValidationStep';
import { AgentChat } from './components/AgentChat';
import { FineTuningMode } from './components/finetuning';
import { DRUG_TARGETS } from './data/drugs';

// Context hooks
import { useGateway } from './contexts/GatewayContext';
import { useWorkflow } from './contexts/WorkflowContext';
import { useWorkflowData } from './contexts/WorkflowDataContext';

import './styles/design-tokens.css';
import './styles/components.css';

function App() {
  // ============================================================================
  // CONTEXT HOOKS - Replace 19+ useState hooks with 3 context hooks
  // ============================================================================

  // Gateway context: connection settings
  const {
    gatewayUrl,
    setGatewayUrl,
    demoModeEnabled,
    setDemoModeEnabled,
    endpoints,
    isCheckingHealth,
    isConnected,
    runHealthCheck,
  } = useGateway();

  // Workflow context: navigation and drug selection
  const {
    workflowMode,
    setWorkflowMode,
    selectedDrugId,
    selectedDrug,
    selectDrug,
    steps,
    currentStepId,
    goToNextStep,
    goToPrevStep,
    handleStepClick,
    customPrompt,
    setCustomPrompt,
    resetWorkflow,
  } = useWorkflow();

  // Workflow data context: results flowing between steps
  const {
    researchPlan,
    setResearchPlan,
    identifiedUniprotId,
    setIdentifiedUniprotId,
    proteinInfo,
    setProteinInfo,
    selectedStructureModel,
    setSelectedStructureModel,
    structureResult,
    setStructureResult,
    generatedMolecules,
    setGeneratedMolecules,
    dockingResults,
    setDockingResults,
    proteinDesignResult,
    setProteinDesignResult,
    sequenceDesignResult,
    setSequenceDesignResult,
    selectedDesignSequenceIndex,
    setSelectedDesignSequenceIndex,
    setValidationResult,
    resetAllData,
  } = useWorkflowData();

  // ============================================================================
  // HANDLERS
  // ============================================================================

  // Handle drug selection
  const handleSelectDrug = useCallback((drugId: string | null) => {
    selectDrug(drugId);
  }, [selectDrug]);

  // Handle switching back from agent mode
  const handleAgentBack = useCallback(() => {
    setWorkflowMode('steps');
    resetWorkflow();
  }, [setWorkflowMode, resetWorkflow]);

  // Handle restart from summary
  const handleRestart = useCallback(() => {
    resetWorkflow();
    resetAllData();
  }, [resetWorkflow, resetAllData]);

  // ============================================================================
  // RENDER STEP CONTENT
  // ============================================================================

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
      case 'target-structure':
        return (
          <StructureStep
            proteinInfo={proteinInfo}
            gatewayUrl={gatewayUrl}
            selectedModel={selectedStructureModel}
            onSelectModel={setSelectedStructureModel}
            onStructureResult={setStructureResult}
            onContinue={goToNextStep}
            onBack={goToPrevStep}
            oligomericState={selectedDrug?.targetProtein.oligomericState}
          />
        );

      case 'protein-design':
        return (
          <ProteinDesignStep
            selectedDrug={selectedDrug}
            gatewayUrl={gatewayUrl}
            targetStructure={structureResult?.structure}
            targetStructureFormat={structureResult?.format}
            onDesignResult={setProteinDesignResult}
            onContinue={goToNextStep}
            onBack={goToPrevStep}
          />
        );

      case 'sequence-design':
        return (
          <SequenceDesignStep
            designedStructure={proteinDesignResult}
            gatewayUrl={gatewayUrl}
            onSequenceResult={(result) => {
              setSequenceDesignResult(result);
              setSelectedDesignSequenceIndex(0);
            }}
            onContinue={goToNextStep}
            onBack={goToPrevStep}
          />
        );

      case 'validation':
        return (
          <ValidationStep
            designedStructure={proteinDesignResult}
            sequenceResult={sequenceDesignResult}
            selectedSequenceIndex={selectedDesignSequenceIndex}
            gatewayUrl={gatewayUrl}
            onValidationResult={setValidationResult}
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
            onRestart={handleRestart}
          />
        );

      default:
        return null;
    }
  };

  // ============================================================================
  // RENDER
  // ============================================================================

  return (
    <div className="app-layout">
      <div className="bg-pattern" />
      <Header isConnected={isConnected} />

      <main className="app-main">
        {workflowMode === 'finetuning' ? (
          <FineTuningMode
            gatewayUrl={gatewayUrl}
            onGatewayUrlChange={setGatewayUrl}
            onBack={() => setWorkflowMode('agent')}
          />
        ) : workflowMode === 'agent' ? (
          <>
            <WorkflowSidebar
              steps={steps}
              onStepClick={handleStepClick}
              gatewayUrl={gatewayUrl}
              onGatewayUrlChange={setGatewayUrl}
              endpoints={endpoints}
              isCheckingHealth={isCheckingHealth}
              onReconnect={runHealthCheck}
              workflowMode={workflowMode}
              onWorkflowModeChange={setWorkflowMode}
              hideWorkflowSteps={true}
              drugTargets={DRUG_TARGETS}
              selectedDrugId={selectedDrugId}
              onSelectDrug={handleSelectDrug}
              demoMode={demoModeEnabled}
              onDemoModeChange={setDemoModeEnabled}
            />

            <div className="content" style={{ padding: 0 }}>
              <AgentChat
                key={`agent-${selectedDrugId}-${workflowMode}`}
                gatewayUrl={gatewayUrl}
                selectedDrug={selectedDrug}
                onBack={handleAgentBack}
              />
            </div>
          </>
        ) : (
          <>
            <WorkflowSidebar
              steps={steps}
              onStepClick={handleStepClick}
              gatewayUrl={gatewayUrl}
              onGatewayUrlChange={setGatewayUrl}
              endpoints={endpoints}
              isCheckingHealth={isCheckingHealth}
              onReconnect={runHealthCheck}
              workflowMode={workflowMode}
              onWorkflowModeChange={setWorkflowMode}
              demoMode={demoModeEnabled}
              onDemoModeChange={setDemoModeEnabled}
            />

            <div className="content">{renderStepContent()}</div>
          </>
        )}
      </main>
    </div>
  );
}

export default App;
