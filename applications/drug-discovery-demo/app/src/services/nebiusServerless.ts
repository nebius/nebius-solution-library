/**
 * Nebius Serverless Service
 *
 * Service for interacting with Nebius Jobs for model fine-tuning.
 * Supports both molecular (regression) and protein (classification) models.
 */

import type {
  TrainingConfig,
  TrainingStatus,
  TrainingLogEntry,
  TrainingResult,
  EndpointInfo,
  ScreeningResult,
  JobState,
  ModelInfo,
} from '../types/finetuning';

// ============================================================================
// Configuration
// ============================================================================

export interface NebiusConfig {
  apiBaseUrl: string;
  objectStorageBucket: string;
  gpuPlatform: string;
  gpuPreset: string;
  region: string;
}

const DEFAULT_CONFIG: NebiusConfig = {
  apiBaseUrl: '', // Will be set from gateway URL
  objectStorageBucket: 'drug-discovery-models',
  gpuPlatform: 'gpu-h200-sxm',
  gpuPreset: '1gpu-16vcpu-200gb',
  region: 'eu-north1',
};

// GPU pricing (approximate)
const GPU_RATE_PER_HOUR = 6.0; // $6/hour for H200

// ============================================================================
// API Client
// ============================================================================

class NebiusServerlessClient {
  private config: NebiusConfig;

  constructor(config: Partial<NebiusConfig> = {}) {
    this.config = { ...DEFAULT_CONFIG, ...config };
  }

  setApiBaseUrl(url: string) {
    this.config.apiBaseUrl = url;
  }

  // --------------------------------------------------------------------------
  // Training Jobs
  // --------------------------------------------------------------------------

  async startTrainingJob(config: TrainingConfig): Promise<string> {
    const response = await fetch(`${this.config.apiBaseUrl}/api/finetuning/train/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ...config,
        gpuPlatform: this.config.gpuPlatform,
        gpuPreset: this.config.gpuPreset,
        objectStorageBucket: this.config.objectStorageBucket,
      }),
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Failed to start training job: ${error}`);
    }

    const data = await response.json();
    return data.jobId;
  }

  async getTrainingStatus(jobId: string): Promise<TrainingStatus> {
    const response = await fetch(
      `${this.config.apiBaseUrl}/api/finetuning/train/status/${jobId}`
    );

    if (!response.ok) {
      throw new Error(`Failed to get training status: ${response.statusText}`);
    }

    return response.json();
  }

  async getTrainingLogs(jobId: string): Promise<TrainingLogEntry[]> {
    const response = await fetch(
      `${this.config.apiBaseUrl}/api/finetuning/train/logs/${jobId}`
    );

    if (!response.ok) {
      throw new Error(`Failed to get training logs: ${response.statusText}`);
    }

    return response.json();
  }

  async cancelTrainingJob(jobId: string): Promise<void> {
    const response = await fetch(
      `${this.config.apiBaseUrl}/api/finetuning/train/cancel/${jobId}`,
      { method: 'POST' }
    );

    if (!response.ok) {
      throw new Error(`Failed to cancel training job: ${response.statusText}`);
    }
  }

  // --------------------------------------------------------------------------
  // Model Deployment
  // --------------------------------------------------------------------------

  async deployModel(modelId: string, name: string): Promise<EndpointInfo> {
    const response = await fetch(`${this.config.apiBaseUrl}/api/finetuning/deploy`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        modelId,
        name,
        gpuPlatform: this.config.gpuPlatform,
        gpuPreset: this.config.gpuPreset,
      }),
    });

    if (!response.ok) {
      throw new Error(`Failed to deploy model: ${response.statusText}`);
    }

    return response.json();
  }

  async getEndpointStatus(endpointId: string): Promise<EndpointInfo> {
    const response = await fetch(
      `${this.config.apiBaseUrl}/api/finetuning/endpoints/${endpointId}`
    );

    if (!response.ok) {
      throw new Error(`Failed to get endpoint status: ${response.statusText}`);
    }

    return response.json();
  }

  async deleteEndpoint(endpointId: string): Promise<void> {
    const response = await fetch(
      `${this.config.apiBaseUrl}/api/finetuning/endpoints/${endpointId}`,
      { method: 'DELETE' }
    );

    if (!response.ok) {
      throw new Error(`Failed to delete endpoint: ${response.statusText}`);
    }
  }

  // --------------------------------------------------------------------------
  // Inference
  // --------------------------------------------------------------------------

  async predict(
    endpointId: string,
    smiles: string[],
    authToken?: string
  ): Promise<ScreeningResult[]> {
    const response = await fetch(
      `${this.config.apiBaseUrl}/api/finetuning/predict/${endpointId}`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(authToken && { Authorization: `Bearer ${authToken}` }),
        },
        body: JSON.stringify({ smiles }),
      }
    );

    if (!response.ok) {
      throw new Error(`Prediction failed: ${response.statusText}`);
    }

    return response.json();
  }
}

// ============================================================================
// Training Simulation (Demo Mode)
// ============================================================================

export interface TrainingSimulationCallbacks {
  onStatusUpdate: (status: TrainingStatus) => void;
  onLogEntry: (entry: Omit<TrainingLogEntry, 'timestamp'>) => void;
  onComplete: (result: TrainingResult) => void;
  onError: (error: string) => void;
}

/**
 * Simulate training progress for demo mode.
 * Supports both molecular (regression) and protein (classification) models.
 */
export async function simulateTraining(
  config: TrainingConfig,
  datasetSize: number,
  callbacks: TrainingSimulationCallbacks,
  signal?: AbortSignal,
  modelInfo?: ModelInfo
): Promise<void> {
  const { onStatusUpdate, onLogEntry, onComplete, onError } = callbacks;
  const { hyperparameters } = config;
  const totalEpochs = hyperparameters.epochs;
  const stepsPerEpoch = Math.ceil(datasetSize / hyperparameters.batchSize);

  const isClassification = modelInfo?.taskType === 'classification';
  const isProtein = modelInfo?.modality === 'protein';
  const modelName = modelInfo?.name || config.baseModel;

  const jobId = `ft-demo-${Date.now().toString(36)}`;
  const startTime = Date.now();

  // Helper to create status object
  const createStatus = (
    state: JobState,
    epoch: number,
    step: number,
    metrics: Partial<TrainingStatus['metrics']> = {}
  ): TrainingStatus => {
    const elapsed = Date.now() - startTime;
    const progress = (epoch - 1 + step / stepsPerEpoch) / totalEpochs;
    const estimatedTotal = progress > 0 ? elapsed / progress : 600000;
    const remaining = Math.max(0, estimatedTotal - elapsed);

    return {
      jobId,
      state,
      progress: {
        epoch,
        totalEpochs,
        step,
        totalSteps: stepsPerEpoch,
        percentage: progress * 100,
      },
      metrics: {
        epoch,
        step,
        loss: metrics.loss ?? 0,
        valR2: metrics.valR2,
        valMae: metrics.valMae,
        valRmse: metrics.valRmse,
        valAccuracy: metrics.valAccuracy,
        valF1: metrics.valF1,
        learningRate: hyperparameters.learningRate,
      },
      timing: {
        startTime,
        elapsedTime: elapsed,
        estimatedTimeRemaining: remaining,
      },
      cost: {
        gpuTimeSeconds: elapsed / 1000,
        estimatedCost: (elapsed / 1000 / 3600) * GPU_RATE_PER_HOUR,
        ratePerHour: GPU_RATE_PER_HOUR,
      },
      gpu: {
        platform: 'gpu-h200-sxm',
        preset: '1gpu-16vcpu-200gb',
        utilization: 80 + Math.random() * 15,
      },
    };
  };

  const sleep = (ms: number) =>
    new Promise<void>((resolve, reject) => {
      const timeout = setTimeout(resolve, ms);
      signal?.addEventListener('abort', () => {
        clearTimeout(timeout);
        reject(new Error('Training cancelled'));
      });
    });

  try {
    // Phase 1: Initialization
    onStatusUpdate(createStatus('pending', 0, 0));
    onLogEntry({ level: 'info', message: 'Requesting Nebius Jobs GPU...', emoji: '🚀' });
    await sleep(1500);

    if (signal?.aborted) throw new Error('Training cancelled');

    onStatusUpdate(createStatus('initializing', 0, 0));
    onLogEntry({
      level: 'success',
      message: 'GPU allocated: gpu-h200-sxm (cold start: 7.2s)',
      emoji: '✓',
    });
    await sleep(1000);

    onLogEntry({ level: 'info', message: `Loading ${modelName} base model...`, emoji: '📦' });
    await sleep(1500);

    onLogEntry({
      level: 'info',
      message: `Dataset loaded: ${Math.floor(datasetSize * 0.8)} train / ${Math.floor(datasetSize * 0.1)} val ${isProtein ? 'sequences' : 'samples'}`,
      emoji: '📊',
    });
    await sleep(500);

    // Phase 2: Training
    let bestValR2 = 0;
    let bestValAcc = 0;
    let bestValF1 = 0;
    let bestLoss = Infinity;

    for (let epoch = 1; epoch <= totalEpochs; epoch++) {
      if (signal?.aborted) throw new Error('Training cancelled');

      // Simulate steps within epoch
      for (let step = 1; step <= stepsPerEpoch; step += Math.ceil(stepsPerEpoch / 5)) {
        if (signal?.aborted) throw new Error('Training cancelled');

        const progress = (epoch - 1 + step / stepsPerEpoch) / totalEpochs;
        const baseLoss = 0.9 * Math.exp(-3 * progress) + 0.15;
        const loss = baseLoss + (Math.random() - 0.5) * 0.05;

        onStatusUpdate(
          createStatus('running', epoch, step, { loss })
        );

        await sleep(80);
      }

      // End of epoch - calculate validation metrics
      const epochProgress = epoch / totalEpochs;
      const epochLoss = 0.9 * Math.exp(-3 * epochProgress) + 0.15;

      bestLoss = Math.min(bestLoss, epochLoss);

      if (isClassification) {
        // Classification metrics: accuracy, F1
        const valAccuracy = 0.55 + 0.35 * (1 - Math.exp(-4 * epochProgress)) + (Math.random() - 0.5) * 0.02;
        const valF1 = 0.50 + 0.38 * (1 - Math.exp(-4 * epochProgress)) + (Math.random() - 0.5) * 0.02;

        bestValAcc = Math.max(bestValAcc, valAccuracy);
        bestValF1 = Math.max(bestValF1, valF1);

        onStatusUpdate(
          createStatus('running', epoch, stepsPerEpoch, {
            loss: epochLoss,
            valAccuracy,
            valF1,
          })
        );

        onLogEntry({
          level: 'success',
          message: `Epoch ${epoch}/${totalEpochs} - Loss: ${epochLoss.toFixed(3)} - Val Acc: ${valAccuracy.toFixed(3)} - Val F1: ${valF1.toFixed(3)}`,
          emoji: '✓',
        });
      } else {
        // Regression metrics: R², MAE
        const valR2 = 0.5 + 0.4 * (1 - Math.exp(-4 * epochProgress)) + (Math.random() - 0.5) * 0.02;
        const valMae = 0.6 * Math.exp(-2 * epochProgress) + 0.25 + (Math.random() - 0.5) * 0.02;
        const valRmse = valMae * 1.3;

        bestValR2 = Math.max(bestValR2, valR2);

        onStatusUpdate(
          createStatus('running', epoch, stepsPerEpoch, {
            loss: epochLoss,
            valR2,
            valMae,
            valRmse,
          })
        );

        onLogEntry({
          level: 'success',
          message: `Epoch ${epoch}/${totalEpochs} - Loss: ${epochLoss.toFixed(3)} - Val R²: ${valR2.toFixed(3)}`,
          emoji: '✓',
        });
      }

      // Check early stopping
      if (hyperparameters.earlyStoppingEnabled && epoch > 3) {
        if (epoch > totalEpochs - 2 && Math.random() > 0.7) {
          onLogEntry({
            level: 'info',
            message: 'Early stopping triggered - validation loss not improving',
            emoji: '⏹️',
          });
          break;
        }
      }
    }

    // Phase 3: Completion
    const finalElapsed = Date.now() - startTime;

    onLogEntry({ level: 'info', message: 'Saving model to Nebius Object Storage...', emoji: '💾' });
    await sleep(1000);

    onLogEntry({
      level: 'success',
      message: `Training complete! Total time: ${formatDuration(finalElapsed)}`,
      emoji: '🎉',
    });

    const result: TrainingResult = {
      jobId,
      modelId: `model-${Date.now().toString(36)}`,
      modelPath: `s3://drug-discovery-models/finetuned/${jobId}/model.pt`,
      finalMetrics: {
        trainLoss: bestLoss,
        valLoss: bestLoss * 1.1,
        testR2: isClassification ? 0 : bestValR2 - 0.01,
        testMae: isClassification ? 0 : 0.3,
        testRmse: isClassification ? 0 : 0.4,
        ...(isClassification && {
          testAccuracy: bestValAcc - 0.005,
          testF1: bestValF1 - 0.01,
          testAucRoc: bestValAcc + 0.02,
        }),
      },
      trainingTime: finalElapsed,
      totalCost: 0,
    };

    onStatusUpdate({ ...createStatus('completed', totalEpochs, stepsPerEpoch), state: 'completed' });
    onComplete(result);
  } catch (err) {
    if (signal?.aborted) {
      onStatusUpdate(createStatus('cancelled', 0, 0));
      onLogEntry({ level: 'warning', message: 'Training cancelled by user', emoji: '⚠️' });
    } else {
      onStatusUpdate(createStatus('failed', 0, 0));
      onError(err instanceof Error ? err.message : 'Training failed');
    }
  }
}

// Helper function
function formatDuration(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  if (minutes > 0) {
    return `${minutes}m ${remainingSeconds}s`;
  }
  return `${seconds}s`;
}

// ============================================================================
// Exports
// ============================================================================

// Singleton instance
let clientInstance: NebiusServerlessClient | null = null;

export function getNebiusClient(config?: Partial<NebiusConfig>): NebiusServerlessClient {
  if (!clientInstance) {
    clientInstance = new NebiusServerlessClient(config);
  } else {
    if (config?.apiBaseUrl) {
      clientInstance.setApiBaseUrl(config.apiBaseUrl);
    }
  }
  return clientInstance;
}

export { NebiusServerlessClient };
