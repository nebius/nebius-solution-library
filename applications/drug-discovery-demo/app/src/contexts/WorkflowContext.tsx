/**
 * Workflow Context
 *
 * Manages the workflow navigation state, including:
 * - Current workflow mode (steps vs agent)
 * - Current step index and navigation
 * - Selected drug target
 * - Workflow type determination
 *
 * This context eliminates navigation-related prop drilling.
 */

import {
  createContext,
  useContext,
  useState,
  useCallback,
  useMemo,
  type ReactNode,
} from 'react';
import type { WorkflowStep, WorkflowStepId, WorkflowType } from '../types/workflow';
import { getDrugById, type DrugTarget } from '../data/drugs';

// Step definitions for each workflow type
type StepDef = { id: WorkflowStepId; title: string; subtitle: string };

const SMALL_MOLECULE_STEPS: StepDef[] = [
  { id: 'use-case', title: 'Drug Target', subtitle: 'Select drug to rediscover' },
  { id: 'sequence', title: 'Sequence', subtitle: 'Fetch from UniProt' },
  { id: 'structure', title: 'Structure', subtitle: 'Predict target protein' },
  { id: 'molecules', title: 'Molecules', subtitle: 'Generate candidates' },
  { id: 'docking', title: 'Docking', subtitle: 'DiffDock validation' },
  { id: 'rediscovery', title: 'Rediscovery', subtitle: 'Score similarity' },
  { id: 'summary', title: 'Summary', subtitle: 'Results & insights' },
];

const PROTEIN_BINDER_STEPS: StepDef[] = [
  { id: 'use-case', title: 'Design Goal', subtitle: 'Select binder target' },
  { id: 'sequence', title: 'Target Sequence', subtitle: 'Fetch from UniProt' },
  { id: 'target-structure', title: 'Target Structure', subtitle: 'Predict target protein' },
  { id: 'protein-design', title: 'Binder Design', subtitle: 'RFDiffusion backbone' },
  { id: 'sequence-design', title: 'Sequence Design', subtitle: 'ProteinMPNN' },
  { id: 'validation', title: 'Validation', subtitle: 'Verify folding' },
  { id: 'summary', title: 'Summary', subtitle: 'Results & insights' },
];

const DE_NOVO_PROTEIN_STEPS: StepDef[] = [
  { id: 'use-case', title: 'Design Goal', subtitle: 'Define protein specs' },
  { id: 'protein-design', title: 'Structure Design', subtitle: 'RFDiffusion backbone' },
  { id: 'sequence-design', title: 'Sequence Design', subtitle: 'ProteinMPNN' },
  { id: 'validation', title: 'Validation', subtitle: 'Verify folding' },
  { id: 'summary', title: 'Summary', subtitle: 'Results & insights' },
];

const ENZYME_ENGINEERING_STEPS: StepDef[] = [
  { id: 'use-case', title: 'Enzyme Target', subtitle: 'Select enzyme' },
  { id: 'sequence', title: 'Sequence', subtitle: 'Fetch from UniProt' },
  { id: 'structure', title: 'Structure', subtitle: 'Predict enzyme structure' },
  { id: 'summary', title: 'Summary', subtitle: 'Analysis & insights' },
];

function getStepsForWorkflowType(workflowType: WorkflowType): StepDef[] {
  switch (workflowType) {
    case 'small-molecule':
      return SMALL_MOLECULE_STEPS;
    case 'protein-binder':
      return PROTEIN_BINDER_STEPS;
    case 'de-novo-protein':
      return DE_NOVO_PROTEIN_STEPS;
    case 'enzyme-engineering':
      return ENZYME_ENGINEERING_STEPS;
    default:
      return SMALL_MOLECULE_STEPS;
  }
}

export type WorkflowMode = 'steps' | 'finetuning' | 'playground';

export interface WorkflowContextValue {
  // Mode
  workflowMode: WorkflowMode;
  setWorkflowMode: (mode: WorkflowMode) => void;

  // Drug selection
  selectedDrugId: string | null;
  selectedDrug: DrugTarget | null;
  selectDrug: (drugId: string | null) => void;

  // Workflow type (derived from selected drug)
  workflowType: WorkflowType;

  // Steps
  steps: WorkflowStep[];
  currentStepIndex: number;
  furthestStepIndex: number;
  currentStepId: WorkflowStepId;

  // Navigation
  goToStep: (stepId: WorkflowStepId) => void;
  goToNextStep: () => void;
  goToPrevStep: () => void;
  handleStepClick: (stepId: WorkflowStepId) => void;
  canNavigateToStep: (stepId: WorkflowStepId) => boolean;

  // Custom prompt (for custom drug discovery)
  customPrompt: string;
  setCustomPrompt: (prompt: string) => void;

  // Reset
  resetWorkflow: () => void;
}

const WorkflowContext = createContext<WorkflowContextValue | null>(null);

export interface WorkflowProviderProps {
  children: ReactNode;
  initialMode?: WorkflowMode;
  onDrugChange?: (drugId: string | null, previousDrugId: string | null) => void;
}

export function WorkflowProvider({
  children,
  initialMode = 'steps',
  onDrugChange,
}: WorkflowProviderProps) {
  const [workflowMode, setWorkflowMode] = useState<WorkflowMode>(initialMode);
  const [selectedDrugId, setSelectedDrugId] = useState<string | null>(null);
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [furthestStepIndex, setFurthestStepIndex] = useState(0);
  const [customPrompt, setCustomPrompt] = useState('');

  // Get selected drug details
  const selectedDrug = useMemo(
    () => (selectedDrugId ? getDrugById(selectedDrugId) ?? null : null),
    [selectedDrugId]
  );

  // Determine workflow type from selected drug
  const workflowType: WorkflowType = selectedDrug?.workflowType || 'small-molecule';

  // Get steps for current workflow type
  const workflowSteps = useMemo(() => getStepsForWorkflowType(workflowType), [workflowType]);

  // Derived: current step ID
  const currentStepId = workflowSteps[currentStepIndex]?.id || 'use-case';

  // Derived: steps with status
  const steps: WorkflowStep[] = useMemo(() => {
    return workflowSteps.map((step, index) => {
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
  }, [workflowSteps, currentStepIndex, furthestStepIndex]);

  // Select drug with reset callback
  const selectDrug = useCallback((drugId: string | null) => {
    const previousDrugId = selectedDrugId;
    if (drugId !== previousDrugId) {
      // Notify parent of drug change (for resetting workflow data)
      onDrugChange?.(drugId, previousDrugId);
      // Reset navigation
      setFurthestStepIndex(0);
      setCurrentStepIndex(0);
    }
    setSelectedDrugId(drugId);
  }, [selectedDrugId, onDrugChange]);

  // Navigation
  const goToStep = useCallback((stepId: WorkflowStepId) => {
    const index = workflowSteps.findIndex((s) => s.id === stepId);
    if (index !== -1) {
      setCurrentStepIndex(index);
    }
  }, [workflowSteps]);

  const goToNextStep = useCallback(() => {
    const nextIndex = currentStepIndex + 1;
    if (nextIndex < workflowSteps.length) {
      setCurrentStepIndex(nextIndex);
      setFurthestStepIndex((prev) => Math.max(prev, nextIndex));
    }
  }, [currentStepIndex, workflowSteps.length]);

  const goToPrevStep = useCallback(() => {
    if (currentStepIndex > 0) {
      setCurrentStepIndex(currentStepIndex - 1);
    }
  }, [currentStepIndex]);

  const canNavigateToStep = useCallback((stepId: WorkflowStepId) => {
    const clickedIndex = workflowSteps.findIndex((s) => s.id === stepId);
    return clickedIndex <= furthestStepIndex;
  }, [workflowSteps, furthestStepIndex]);

  const handleStepClick = useCallback((stepId: WorkflowStepId) => {
    if (canNavigateToStep(stepId)) {
      goToStep(stepId);
    }
  }, [canNavigateToStep, goToStep]);

  // Full reset
  const resetWorkflow = useCallback(() => {
    setCurrentStepIndex(0);
    setFurthestStepIndex(0);
    setSelectedDrugId(null);
    setCustomPrompt('');
  }, []);

  const value: WorkflowContextValue = useMemo(() => ({
    workflowMode,
    setWorkflowMode,
    selectedDrugId,
    selectedDrug,
    selectDrug,
    workflowType,
    steps,
    currentStepIndex,
    furthestStepIndex,
    currentStepId,
    goToStep,
    goToNextStep,
    goToPrevStep,
    handleStepClick,
    canNavigateToStep,
    customPrompt,
    setCustomPrompt,
    resetWorkflow,
  }), [workflowMode, setWorkflowMode, selectedDrugId, selectedDrug, selectDrug, workflowType, steps, currentStepIndex, furthestStepIndex, currentStepId, goToStep, goToNextStep, goToPrevStep, handleStepClick, canNavigateToStep, customPrompt, setCustomPrompt, resetWorkflow]);

  return (
    <WorkflowContext.Provider value={value}>
      {children}
    </WorkflowContext.Provider>
  );
}

/**
 * Hook to access the workflow context
 *
 * @throws Error if used outside of WorkflowProvider
 */
export function useWorkflow(): WorkflowContextValue {
  const context = useContext(WorkflowContext);
  if (!context) {
    throw new Error('useWorkflow must be used within a WorkflowProvider');
  }
  return context;
}

/**
 * Hook to get just the selected drug (convenience hook)
 */
export function useSelectedDrug(): DrugTarget | null {
  const { selectedDrug } = useWorkflow();
  return selectedDrug;
}

/**
 * Hook to get navigation functions (convenience hook)
 */
export function useWorkflowNavigation() {
  const { goToNextStep, goToPrevStep, goToStep, handleStepClick, canNavigateToStep } = useWorkflow();
  return { goToNextStep, goToPrevStep, goToStep, handleStepClick, canNavigateToStep };
}
