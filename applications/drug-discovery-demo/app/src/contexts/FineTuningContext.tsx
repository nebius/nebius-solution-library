/**
 * Fine-Tuning Context
 *
 * Manages state for the Nebius Serverless Fine-Tuning workflow:
 * - Dataset selection and validation
 * - Model configuration
 * - Training job management
 * - Evaluation results
 * - Deployment and screening
 */

import {
  createContext,
  useContext,
  useState,
  useCallback,
  useMemo,
  type ReactNode,
} from 'react';
import type {
  DataSourceType,
  DatasetInfo,
  BaseModelId,
  HyperParameters,
  TrainingStatus,
  TrainingLogEntry,
  TrainingResult,
  EvaluationResult,
  EndpointInfo,
  ScreeningResult,
  FineTuningStep,
  FineTuningStepId,
} from '../types/finetuning';

// Re-import steps constant
const STEPS: Omit<FineTuningStep, 'status'>[] = [
  { id: 'data-selection', title: 'Data', subtitle: 'Select training data' },
  { id: 'data-preview', title: 'Preview', subtitle: 'Review & validate' },
  { id: 'model-config', title: 'Configure', subtitle: 'Model & parameters' },
  { id: 'training', title: 'Train', subtitle: 'Nebius Serverless' },
  { id: 'evaluation', title: 'Evaluate', subtitle: 'Model performance' },
  { id: 'screening', title: 'Screen', subtitle: 'Deploy & predict' },
];

// Default hyperparameters
const DEFAULT_HYPERPARAMETERS: HyperParameters = {
  epochs: 10,
  batchSize: 32,
  learningRate: 1e-5,
  weightDecay: 0.01,
  warmupSteps: 100,
  earlyStoppingEnabled: true,
  earlyStoppingPatience: 3,
};

export interface FineTuningContextValue {
  // Navigation
  currentStepIndex: number;
  currentStepId: FineTuningStepId;
  furthestStepIndex: number;
  steps: FineTuningStep[];
  goToStep: (stepId: FineTuningStepId) => void;
  goToNextStep: () => void;
  goToPrevStep: () => void;
  canNavigateToStep: (stepId: FineTuningStepId) => boolean;

  // Data selection
  dataSource: DataSourceType | null;
  setDataSource: (source: DataSourceType | null) => void;
  dataset: DatasetInfo | null;
  setDataset: (dataset: DatasetInfo | null) => void;

  // Model configuration
  baseModel: BaseModelId;
  setBaseModel: (model: BaseModelId) => void;
  hyperparameters: HyperParameters;
  setHyperparameters: (params: HyperParameters) => void;
  updateHyperparameter: <K extends keyof HyperParameters>(
    key: K,
    value: HyperParameters[K]
  ) => void;

  // Training
  trainingJobId: string | null;
  setTrainingJobId: (jobId: string | null) => void;
  trainingStatus: TrainingStatus | null;
  setTrainingStatus: (status: TrainingStatus | null) => void;
  trainingLogs: TrainingLogEntry[];
  addTrainingLog: (entry: Omit<TrainingLogEntry, 'timestamp'>) => void;
  clearTrainingLogs: () => void;
  trainingResult: TrainingResult | null;
  setTrainingResult: (result: TrainingResult | null) => void;

  // Evaluation
  evaluationResult: EvaluationResult | null;
  setEvaluationResult: (result: EvaluationResult | null) => void;

  // Deployment
  endpoint: EndpointInfo | null;
  setEndpoint: (endpoint: EndpointInfo | null) => void;

  // Screening
  screeningResults: ScreeningResult[] | null;
  setScreeningResults: (results: ScreeningResult[] | null) => void;

  // Reset
  resetAll: () => void;
}

const FineTuningContext = createContext<FineTuningContextValue | null>(null);

export interface FineTuningProviderProps {
  children: ReactNode;
}

export function FineTuningProvider({ children }: FineTuningProviderProps) {
  // Navigation state
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [furthestStepIndex, setFurthestStepIndex] = useState(0);

  // Data state
  const [dataSource, setDataSource] = useState<DataSourceType | null>(null);
  const [dataset, setDataset] = useState<DatasetInfo | null>(null);

  // Model config state
  const [baseModel, setBaseModel] = useState<BaseModelId>('chemberta-77m-mtr');
  const [hyperparameters, setHyperparameters] = useState<HyperParameters>(
    DEFAULT_HYPERPARAMETERS
  );

  // Training state
  const [trainingJobId, setTrainingJobId] = useState<string | null>(null);
  const [trainingStatus, setTrainingStatus] = useState<TrainingStatus | null>(null);
  const [trainingLogs, setTrainingLogs] = useState<TrainingLogEntry[]>([]);
  const [trainingResult, setTrainingResult] = useState<TrainingResult | null>(null);

  // Evaluation state
  const [evaluationResult, setEvaluationResult] = useState<EvaluationResult | null>(null);

  // Deployment state
  const [endpoint, setEndpoint] = useState<EndpointInfo | null>(null);

  // Screening state
  const [screeningResults, setScreeningResults] = useState<ScreeningResult[] | null>(null);

  // Derived: current step ID
  const currentStepId = STEPS[currentStepIndex]?.id || 'data-selection';

  // Derived: steps with status
  const steps: FineTuningStep[] = useMemo(() => {
    return STEPS.map((step, index) => {
      let status: FineTuningStep['status'];
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

  // Navigation
  const goToStep = useCallback((stepId: FineTuningStepId) => {
    const index = STEPS.findIndex((s) => s.id === stepId);
    if (index !== -1) {
      setCurrentStepIndex(index);
    }
  }, []);

  const goToNextStep = useCallback(() => {
    const nextIndex = currentStepIndex + 1;
    if (nextIndex < STEPS.length) {
      setCurrentStepIndex(nextIndex);
      setFurthestStepIndex((prev) => Math.max(prev, nextIndex));
    }
  }, [currentStepIndex]);

  const goToPrevStep = useCallback(() => {
    if (currentStepIndex > 0) {
      setCurrentStepIndex(currentStepIndex - 1);
    }
  }, [currentStepIndex]);

  const canNavigateToStep = useCallback(
    (stepId: FineTuningStepId) => {
      const index = STEPS.findIndex((s) => s.id === stepId);
      return index <= furthestStepIndex;
    },
    [furthestStepIndex]
  );

  // Hyperparameter update helper
  const updateHyperparameter = useCallback(
    <K extends keyof HyperParameters>(key: K, value: HyperParameters[K]) => {
      setHyperparameters((prev) => ({ ...prev, [key]: value }));
    },
    []
  );

  // Training log helper
  const addTrainingLog = useCallback(
    (entry: Omit<TrainingLogEntry, 'timestamp'>) => {
      setTrainingLogs((prev) => [...prev, { ...entry, timestamp: Date.now() }]);
    },
    []
  );

  const clearTrainingLogs = useCallback(() => {
    setTrainingLogs([]);
  }, []);

  // Reset all state
  const resetAll = useCallback(() => {
    setCurrentStepIndex(0);
    setFurthestStepIndex(0);
    setDataSource(null);
    setDataset(null);
    setBaseModel('chemberta-77m-mtr');
    setHyperparameters(DEFAULT_HYPERPARAMETERS);
    setTrainingJobId(null);
    setTrainingStatus(null);
    setTrainingLogs([]);
    setTrainingResult(null);
    setEvaluationResult(null);
    setEndpoint(null);
    setScreeningResults(null);
  }, []);

  const value: FineTuningContextValue = {
    // Navigation
    currentStepIndex,
    currentStepId,
    furthestStepIndex,
    steps,
    goToStep,
    goToNextStep,
    goToPrevStep,
    canNavigateToStep,

    // Data
    dataSource,
    setDataSource,
    dataset,
    setDataset,

    // Model config
    baseModel,
    setBaseModel,
    hyperparameters,
    setHyperparameters,
    updateHyperparameter,

    // Training
    trainingJobId,
    setTrainingJobId,
    trainingStatus,
    setTrainingStatus,
    trainingLogs,
    addTrainingLog,
    clearTrainingLogs,
    trainingResult,
    setTrainingResult,

    // Evaluation
    evaluationResult,
    setEvaluationResult,

    // Deployment
    endpoint,
    setEndpoint,

    // Screening
    screeningResults,
    setScreeningResults,

    // Reset
    resetAll,
  };

  return (
    <FineTuningContext.Provider value={value}>
      {children}
    </FineTuningContext.Provider>
  );
}

/**
 * Hook to access the fine-tuning context
 */
export function useFineTuning(): FineTuningContextValue {
  const context = useContext(FineTuningContext);
  if (!context) {
    throw new Error('useFineTuning must be used within a FineTuningProvider');
  }
  return context;
}
