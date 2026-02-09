/**
 * Fine-Tuning Types
 *
 * Type definitions for the Nebius Serverless Fine-Tuning workflow.
 */

// ============================================================================
// Data Types
// ============================================================================

export type DataSourceType = 'chembl' | 'upload' | 'demo';

export interface ChemBLTarget {
  chemblId: string;
  name: string;
  organism: string;
  targetType: string;
  compoundCount: number;
}

export interface DatasetMolecule {
  smiles: string;
  activity: number;
  activityUnit: string;
  isValid: boolean;
  molecularWeight?: number;
}

export interface DatasetInfo {
  id: string;
  name: string;
  source: DataSourceType;
  sourceId?: string; // ChEMBL target ID or filename
  activityType: 'IC50' | 'Ki' | 'EC50' | 'Kd' | 'custom';
  activityUnit: string;
  molecules: DatasetMolecule[];
  totalCount: number;
  validCount: number;
  invalidCount: number;
  activityRange: { min: number; max: number };
  molecularWeightRange: { min: number; max: number };
  splits: {
    train: number;
    validation: number;
    test: number;
  };
}

export interface DemoDataset {
  id: string;
  name: string;
  description: string;
  targetName: string;
  chemblId: string;
  activityType: 'IC50' | 'Ki' | 'EC50';
  compoundCount: number;
}

// ============================================================================
// Model Configuration
// ============================================================================

export type BaseModelId = 'chemberta-77m-mtr' | 'chemberta-77m-mlm' | 'molbert-100m';

export interface BaseModel {
  id: BaseModelId;
  name: string;
  description: string;
  parameters: string;
  recommended?: boolean;
  bestFor: string[];
}

export interface HyperParameters {
  epochs: number;
  batchSize: number;
  learningRate: number;
  weightDecay: number;
  warmupSteps: number;
  earlyStoppingEnabled: boolean;
  earlyStoppingPatience: number;
}

export interface TrainingConfig {
  datasetId: string;
  baseModel: BaseModelId;
  hyperparameters: HyperParameters;
  jobName?: string;
}

// ============================================================================
// Nebius Serverless Types
// ============================================================================

export type JobState =
  | 'pending'
  | 'initializing'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled';

export interface TrainingMetrics {
  epoch: number;
  step: number;
  loss: number;
  valLoss?: number;
  valR2?: number;
  valMae?: number;
  valRmse?: number;
  learningRate: number;
}

export interface TrainingStatus {
  jobId: string;
  state: JobState;
  progress: {
    epoch: number;
    totalEpochs: number;
    step: number;
    totalSteps: number;
    percentage: number;
  };
  metrics: TrainingMetrics;
  timing: {
    startTime: number;
    elapsedTime: number;
    estimatedTimeRemaining: number;
  };
  cost: {
    gpuTimeSeconds: number;
    estimatedCost: number;
    ratePerHour: number;
  };
  gpu: {
    platform: string;
    preset: string;
    utilization: number;
  };
  error?: string;
}

export interface TrainingLogEntry {
  timestamp: number;
  level: 'info' | 'warning' | 'error' | 'success';
  message: string;
  emoji?: string;
}

export interface TrainingResult {
  jobId: string;
  modelId: string;
  modelPath: string; // S3/Object Storage path
  finalMetrics: {
    trainLoss: number;
    valLoss: number;
    testR2: number;
    testMae: number;
    testRmse: number;
  };
  trainingTime: number;
  totalCost: number;
}

// ============================================================================
// Evaluation Types
// ============================================================================

export interface EvaluationMetrics {
  r2: number;
  mae: number;
  rmse: number;
  pearsonR: number;
  spearmanR: number;
}

export interface PredictionPoint {
  actual: number;
  predicted: number;
  smiles: string;
  residual: number;
}

export interface EvaluationResult {
  testMetrics: EvaluationMetrics;
  predictions: PredictionPoint[];
  residualStats: {
    mean: number;
    std: number;
    min: number;
    max: number;
  };
  comparisonBaseline?: {
    r2: number;
    mae: number;
    name: string;
  };
}

// ============================================================================
// Deployment Types
// ============================================================================

export type EndpointState = 'creating' | 'ready' | 'failed' | 'deleting';

export interface EndpointInfo {
  endpointId: string;
  name: string;
  url: string;
  state: EndpointState;
  modelId: string;
  createdAt: number;
  platform: string;
  preset: string;
  authToken?: string;
}

// ============================================================================
// Screening Types
// ============================================================================

export interface ScreeningResult {
  smiles: string;
  predictedActivity: number;
  confidence: 'high' | 'medium' | 'low';
  predictedUnit: string;
  rank: number;
}

export interface ScreeningJob {
  id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  totalCompounds: number;
  processedCompounds: number;
  results: ScreeningResult[];
  throughput: number; // compounds per second
  elapsedTime: number;
}

// ============================================================================
// Workflow Types
// ============================================================================

export type FineTuningStepId =
  | 'data-selection'
  | 'data-preview'
  | 'model-config'
  | 'training'
  | 'evaluation'
  | 'screening';

export interface FineTuningStep {
  id: FineTuningStepId;
  title: string;
  subtitle: string;
  status: 'pending' | 'active' | 'completed';
}

export const FINETUNING_STEPS: Omit<FineTuningStep, 'status'>[] = [
  { id: 'data-selection', title: 'Data', subtitle: 'Select training data' },
  { id: 'data-preview', title: 'Preview', subtitle: 'Review & validate' },
  { id: 'model-config', title: 'Configure', subtitle: 'Model & parameters' },
  { id: 'training', title: 'Train', subtitle: 'Nebius Serverless' },
  { id: 'evaluation', title: 'Evaluate', subtitle: 'Model performance' },
  { id: 'screening', title: 'Screen', subtitle: 'Deploy & predict' },
];
