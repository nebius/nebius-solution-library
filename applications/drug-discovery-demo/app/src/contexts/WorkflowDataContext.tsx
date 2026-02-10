/**
 * Workflow Data Context
 *
 * Manages the workflow results/data that flows between steps:
 * - Protein info from UniProt
 * - Structure prediction results
 * - Generated molecules
 * - Docking results
 * - Protein design results (for protein-binder workflow)
 *
 * This context eliminates workflow data prop drilling and provides
 * a centralized place for step components to read/write results.
 */

import {
  createContext,
  useContext,
  useState,
  useCallback,
  useMemo,
  type ReactNode,
} from 'react';
import type { StructurePredictionResult } from '../services/structurePrediction';
import type { GeneratedMolecule } from '../services/moleculeGeneration';
import type { DockingResult } from '../services/docking';

// Import types from step components to ensure consistency
import type { ProteinDesignResult } from '../components/steps/ProteinDesignStep';
import type { SequenceDesignResult } from '../components/steps/SequenceDesignStep';
import type { ValidationResult } from '../components/steps/ValidationStep';

// Protein info from UniProt
export interface ProteinInfo {
  accession: string;
  name: string;
  organism: string;
  sequence: string;
  length: number;
}

// Re-export types from step components for convenience
export type { ProteinDesignResult, SequenceDesignResult, ValidationResult };

export interface WorkflowDataContextValue {
  // UniProt ID (auto-populated from selected drug)
  identifiedUniprotId: string;
  setIdentifiedUniprotId: (id: string) => void;

  // Protein info
  proteinInfo: ProteinInfo | null;
  setProteinInfo: (info: ProteinInfo | null) => void;

  // Structure model selection
  selectedStructureModel: string | null;
  setSelectedStructureModel: (model: string | null) => void;

  // Structure prediction result
  structureResult: StructurePredictionResult | null;
  setStructureResult: (result: StructurePredictionResult | null) => void;

  // Generated molecules
  generatedMolecules: GeneratedMolecule[];
  setGeneratedMolecules: (molecules: GeneratedMolecule[]) => void;

  // Docking results
  dockingResults: DockingResult[];
  setDockingResults: (results: DockingResult[]) => void;

  // Protein design workflow
  proteinDesignResult: ProteinDesignResult | null;
  setProteinDesignResult: (result: ProteinDesignResult | null) => void;

  sequenceDesignResult: SequenceDesignResult | null;
  setSequenceDesignResult: (result: SequenceDesignResult | null) => void;

  selectedDesignSequenceIndex: number;
  setSelectedDesignSequenceIndex: (index: number) => void;

  validationResult: ValidationResult | null;
  setValidationResult: (result: ValidationResult | null) => void;

  // Reset all data
  resetAllData: () => void;
}

const WorkflowDataContext = createContext<WorkflowDataContextValue | null>(null);

export interface WorkflowDataProviderProps {
  children: ReactNode;
}

export function WorkflowDataProvider({ children }: WorkflowDataProviderProps) {
  // UniProt ID (auto-populated from selected drug)
  const [identifiedUniprotId, setIdentifiedUniprotId] = useState('');

  // Protein info
  const [proteinInfo, setProteinInfo] = useState<ProteinInfo | null>(null);

  // Structure
  const [selectedStructureModel, setSelectedStructureModel] = useState<string | null>(null);
  const [structureResult, setStructureResult] = useState<StructurePredictionResult | null>(null);

  // Molecules
  const [generatedMolecules, setGeneratedMolecules] = useState<GeneratedMolecule[]>([]);

  // Docking
  const [dockingResults, setDockingResults] = useState<DockingResult[]>([]);

  // Protein design
  const [proteinDesignResult, setProteinDesignResult] = useState<ProteinDesignResult | null>(null);
  const [sequenceDesignResult, setSequenceDesignResult] = useState<SequenceDesignResult | null>(null);
  const [selectedDesignSequenceIndex, setSelectedDesignSequenceIndex] = useState(0);
  const [validationResult, setValidationResult] = useState<ValidationResult | null>(null);

  // Reset all data (called when drug target changes)
  const resetAllData = useCallback(() => {
    setIdentifiedUniprotId('');
    setProteinInfo(null);
    setSelectedStructureModel(null);
    setStructureResult(null);
    setGeneratedMolecules([]);
    setDockingResults([]);
    setProteinDesignResult(null);
    setSequenceDesignResult(null);
    setSelectedDesignSequenceIndex(0);
    setValidationResult(null);
  }, []);

  const value: WorkflowDataContextValue = useMemo(() => ({
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
    validationResult,
    setValidationResult,
    resetAllData,
  }), [identifiedUniprotId, proteinInfo, selectedStructureModel, structureResult, generatedMolecules, dockingResults, proteinDesignResult, sequenceDesignResult, selectedDesignSequenceIndex, validationResult, resetAllData]);

  return (
    <WorkflowDataContext.Provider value={value}>
      {children}
    </WorkflowDataContext.Provider>
  );
}

/**
 * Hook to access the workflow data context
 *
 * @throws Error if used outside of WorkflowDataProvider
 */
export function useWorkflowData(): WorkflowDataContextValue {
  const context = useContext(WorkflowDataContext);
  if (!context) {
    throw new Error('useWorkflowData must be used within a WorkflowDataProvider');
  }
  return context;
}

/**
 * Hook to get protein info (convenience hook)
 */
export function useProteinInfo() {
  const { proteinInfo, setProteinInfo } = useWorkflowData();
  return { proteinInfo, setProteinInfo };
}

/**
 * Hook to get structure result (convenience hook)
 */
export function useStructureResult() {
  const { structureResult, setStructureResult, selectedStructureModel, setSelectedStructureModel } = useWorkflowData();
  return { structureResult, setStructureResult, selectedStructureModel, setSelectedStructureModel };
}

/**
 * Hook to get molecules (convenience hook)
 */
export function useMolecules() {
  const { generatedMolecules, setGeneratedMolecules } = useWorkflowData();
  return { generatedMolecules, setGeneratedMolecules };
}

/**
 * Hook to get docking results (convenience hook)
 */
export function useDockingResults() {
  const { dockingResults, setDockingResults } = useWorkflowData();
  return { dockingResults, setDockingResults };
}
