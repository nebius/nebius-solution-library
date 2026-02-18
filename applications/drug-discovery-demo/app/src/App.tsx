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
import { SequenceStep } from './components/steps/SequenceStep';
import { StructureStep } from './components/steps/StructureStep';
import { MoleculesStep } from './components/steps/MoleculesStep';
import { DockingStep } from './components/steps/DockingStep';
import { RediscoveryStep } from './components/steps/RediscoveryStep';
import { SummaryStep } from './components/steps/SummaryStep';
import { ProteinDesignStep } from './components/steps/ProteinDesignStep';
import { SequenceDesignStep } from './components/steps/SequenceDesignStep';
import { ValidationStep } from './components/steps/ValidationStep';
import { FineTuningMode } from './components/finetuning';
import { NimPlayground } from './components/playground';
import { DRUG_TARGETS, getDrugById } from './data/drugs';

// Context hooks
import { useGateway } from './contexts/GatewayContext';
import { useWorkflow } from './contexts/WorkflowContext';
import { useWorkflowData } from './contexts/WorkflowDataContext';

import './styles/index.css';

function App() {
  // ============================================================================
  // CONTEXT HOOKS - Replace 19+ useState hooks with 3 context hooks
  // ============================================================================

  // Gateway context: connection settings
  const {
    gatewayUrl,
    isConnected,
  } = useGateway();

  // Workflow context: navigation and drug selection
  const {
    workflowMode,
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

  // Handle drug selection — auto-populate UniProt ID from drug data
  const handleSelectDrug = useCallback((drugId: string | null) => {
    selectDrug(drugId);
    if (drugId) {
      const drug = getDrugById(drugId);
      if (drug?.targetProtein.uniprotId) {
        setIdentifiedUniprotId(drug.targetProtein.uniprotId);
      }
    }
  }, [selectDrug, setIdentifiedUniprotId]);

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
          <FineTuningMode />
        ) : workflowMode === 'playground' ? (
          <NimPlayground />
        ) : (
          <>
            <WorkflowSidebar
              steps={steps}
              onStepClick={handleStepClick}
            />

            <div className="content">{renderStepContent()}</div>
          </>
        )}
      </main>
    </div>
  );
}

export default App;
