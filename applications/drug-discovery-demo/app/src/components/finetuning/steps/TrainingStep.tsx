/**
 * TrainingStep Component
 *
 * Fourth step: Execute training on Nebius Serverless with live updates.
 * This is the key showcase of Nebius Serverless capabilities.
 */

import { useState, useCallback, useEffect, useRef } from 'react';
import { useFineTuning } from '../../../contexts/FineTuningContext';
import { simulateTraining } from '../../../services/nebiusServerless';

interface TrainingStepProps {
  gatewayUrl: string;
}

export function TrainingStep({ gatewayUrl }: TrainingStepProps) {
  const {
    dataset,
    baseModel,
    hyperparameters,
    trainingStatus,
    setTrainingStatus,
    trainingLogs,
    addTrainingLog,
    clearTrainingLogs,
    trainingResult,
    setTrainingResult,
    setTrainingJobId,
    goToNextStep,
    goToPrevStep,
  } = useFineTuning();

  const [isStarting, setIsStarting] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Check if training is in progress
  const isTraining = trainingStatus?.state === 'running' || trainingStatus?.state === 'initializing';
  const isCompleted = trainingStatus?.state === 'completed';
  const isFailed = trainingStatus?.state === 'failed';
  const isCancelled = trainingStatus?.state === 'cancelled';

  // Format time
  const formatTime = (ms: number) => {
    const seconds = Math.floor(ms / 1000);
    const minutes = Math.floor(seconds / 60);
    const secs = seconds % 60;
    if (minutes > 0) {
      return `${minutes}m ${secs}s`;
    }
    return `${seconds}s`;
  };

  // Start training
  const handleStartTraining = useCallback(async () => {
    if (!dataset) return;

    setIsStarting(true);
    clearTrainingLogs();
    setTrainingResult(null);

    // Create abort controller for cancellation
    abortControllerRef.current = new AbortController();

    const config = {
      datasetId: dataset.id,
      baseModel,
      hyperparameters,
    };

    // For now, always use simulation (demo mode)
    // In production, this would check gatewayUrl and call real API
    const isDemoMode = !gatewayUrl;

    if (isDemoMode || true) {
      // Simulate training
      setTrainingJobId(`ft-demo-${Date.now().toString(36)}`);
      setIsStarting(false);

      await simulateTraining(
        config,
        dataset.validCount,
        {
          onStatusUpdate: setTrainingStatus,
          onLogEntry: addTrainingLog,
          onComplete: (result) => {
            setTrainingResult(result);
          },
          onError: (error) => {
            addTrainingLog({ level: 'error', message: error, emoji: '❌' });
          },
        },
        abortControllerRef.current.signal
      );
    }
  }, [
    dataset,
    baseModel,
    hyperparameters,
    gatewayUrl,
    clearTrainingLogs,
    setTrainingResult,
    setTrainingJobId,
    setTrainingStatus,
    addTrainingLog,
  ]);

  // Cancel training
  const handleCancelTraining = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
  }, []);

  // Auto-scroll logs
  const logsEndRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [trainingLogs]);

  // Render progress bar
  const progressPercentage = trainingStatus?.progress.percentage ?? 0;

  return (
    <div className="step-content">
      <div className="content-header">
        <div>
          <h1 className="content-title">Training on Nebius Serverless</h1>
          <p className="content-subtitle">
            {isTraining
              ? 'Your model is training on Nebius Serverless GPU...'
              : isCompleted
              ? 'Training complete!'
              : 'Ready to start training'}
          </p>
        </div>
      </div>

      {/* Nebius Serverless Status Banner */}
      <div className={`serverless-banner ${trainingStatus?.state || 'pending'}`}>
        <div className="serverless-banner-icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
            <path
              d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </div>
        <div className="serverless-banner-content">
          <span className="serverless-banner-title">NEBIUS SERVERLESS GPU</span>
          <span className="serverless-banner-status">
            {trainingStatus?.gpu.platform || 'gpu-h200-sxm'} •{' '}
            {trainingStatus?.gpu.preset || '1gpu-16vcpu-200gb'} •{' '}
            {trainingStatus?.state === 'running'
              ? 'Training'
              : trainingStatus?.state === 'initializing'
              ? 'Initializing'
              : trainingStatus?.state === 'completed'
              ? 'Complete'
              : trainingStatus?.state === 'failed'
              ? 'Failed'
              : 'Ready'}
          </span>
        </div>
        {trainingStatus?.jobId && (
          <span className="serverless-banner-jobid">Job: {trainingStatus.jobId}</span>
        )}
      </div>

      {/* Start Training Card (shown when not started) */}
      {!trainingStatus && !isStarting && (
        <div className="card training-start-card">
          <div className="training-start-content">
            <div className="training-start-icon">
              <svg width="64" height="64" viewBox="0 0 64 64" fill="none">
                <rect width="64" height="64" rx="16" fill="var(--color-violet)" />
                <path d="M24 20v24l20-12-20-12z" fill="white" />
              </svg>
            </div>
            <h3 className="training-start-title">Ready to Train</h3>
            <p className="training-start-description">
              Fine-tune {baseModel.replace('-', ' ').toUpperCase()} on{' '}
              {dataset?.validCount.toLocaleString()} compounds for {hyperparameters.epochs} epochs.
            </p>
            <div className="training-start-estimates">
              <span>Est. Time: ~{Math.ceil((dataset?.validCount || 1000) / 100)}m</span>
              <span>•</span>
              <span>Est. Cost: ~${((dataset?.validCount || 1000) / 100 / 60 * 6).toFixed(2)}</span>
            </div>
            <button className="btn btn-primary btn-lg" onClick={handleStartTraining}>
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <path d="M4 4l12 6-12 6V4z" fill="currentColor" />
              </svg>
              Start Training on Nebius
            </button>
          </div>
        </div>
      )}

      {/* Progress Section (shown during training) */}
      {(isTraining || isCompleted || isFailed || isCancelled) && (
        <>
          {/* Progress and Metrics */}
          <div className="training-progress-section">
            <div className="training-progress-card">
              <h4>Progress</h4>
              <div className="progress-bar-container">
                <div
                  className="progress-bar-fill"
                  style={{ width: `${progressPercentage}%` }}
                />
              </div>
              <div className="progress-details">
                <span>
                  Epoch {trainingStatus?.progress.epoch || 0} / {trainingStatus?.progress.totalEpochs || hyperparameters.epochs}
                </span>
                <span>{progressPercentage.toFixed(1)}%</span>
              </div>
              <div className="progress-timing">
                <div className="timing-item">
                  <span className="timing-label">Elapsed</span>
                  <span className="timing-value">
                    {formatTime(trainingStatus?.timing.elapsedTime || 0)}
                  </span>
                </div>
                <div className="timing-item">
                  <span className="timing-label">ETA</span>
                  <span className="timing-value">
                    {isCompleted
                      ? '-'
                      : `~${formatTime(trainingStatus?.timing.estimatedTimeRemaining || 0)}`}
                  </span>
                </div>
              </div>
            </div>

            <div className="training-metrics-card">
              <h4>Live Metrics</h4>
              <div className="metrics-grid">
                <div className="metric-item">
                  <span className="metric-label">Loss</span>
                  <span className="metric-value">
                    {trainingStatus?.metrics.loss?.toFixed(3) || '-'}
                  </span>
                </div>
                <div className="metric-item">
                  <span className="metric-label">Val R²</span>
                  <span className="metric-value highlight">
                    {trainingStatus?.metrics.valR2?.toFixed(3) || '-'}
                  </span>
                </div>
                <div className="metric-item">
                  <span className="metric-label">Val MAE</span>
                  <span className="metric-value">
                    {trainingStatus?.metrics.valMae?.toFixed(3) || '-'}
                  </span>
                </div>
                <div className="metric-item">
                  <span className="metric-label">GPU Util</span>
                  <span className="metric-value">
                    {trainingStatus?.gpu.utilization?.toFixed(0) || '-'}%
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Cost Tracker */}
          <div className="cost-tracker">
            <div className="cost-tracker-icon">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.5" />
                <path d="M8 4v8M6 6h4M6 10h3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
            </div>
            <div className="cost-tracker-content">
              <span className="cost-tracker-label">SERVERLESS COST TRACKER</span>
              <div className="cost-tracker-details">
                <span>
                  GPU Time: {formatTime((trainingStatus?.cost.gpuTimeSeconds || 0) * 1000)}
                </span>
                <span>•</span>
                <span>Current Cost: ${trainingStatus?.cost.estimatedCost?.toFixed(2) || '0.00'}</span>
                <span>•</span>
                <span>Rate: ${trainingStatus?.cost.ratePerHour || 6}/hr</span>
              </div>
            </div>
          </div>

          {/* Training Logs */}
          <div className="card training-logs-card">
            <div className="card-header">
              <h3 className="card-title">Training Log</h3>
              <span className="card-badge">{trainingLogs.length} entries</span>
            </div>
            <div className="training-logs">
              {trainingLogs.map((log, i) => (
                <div key={i} className={`log-entry ${log.level}`}>
                  <span className="log-time">
                    [{new Date(log.timestamp).toLocaleTimeString()}]
                  </span>
                  {log.emoji && <span className="log-emoji">{log.emoji}</span>}
                  <span className="log-message">{log.message}</span>
                </div>
              ))}
              <div ref={logsEndRef} />
            </div>
          </div>
        </>
      )}

      {/* Results Summary (shown when complete) */}
      {isCompleted && trainingResult && (
        <div className="card training-complete-card">
          <div className="card-header">
            <h3 className="card-title">Training Complete</h3>
            <span className="card-badge success">Success</span>
          </div>
          <div className="training-complete-summary">
            <div className="summary-item">
              <span className="summary-label">Final Test R²</span>
              <span className="summary-value highlight">
                {trainingResult.finalMetrics.testR2.toFixed(3)}
              </span>
            </div>
            <div className="summary-item">
              <span className="summary-label">Test MAE</span>
              <span className="summary-value">
                {trainingResult.finalMetrics.testMae.toFixed(3)}
              </span>
            </div>
            <div className="summary-item">
              <span className="summary-label">Training Time</span>
              <span className="summary-value">{formatTime(trainingResult.trainingTime)}</span>
            </div>
            <div className="summary-item">
              <span className="summary-label">Total Cost</span>
              <span className="summary-value">${trainingResult.totalCost.toFixed(2)}</span>
            </div>
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="step-actions">
        <button
          className="btn btn-ghost"
          onClick={goToPrevStep}
          disabled={isTraining}
        >
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M12.5 15l-5-5 5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Back
        </button>

        {isTraining && (
          <button className="btn btn-danger" onClick={handleCancelTraining}>
            Cancel Training
          </button>
        )}

        {isCompleted && (
          <button className="btn btn-primary btn-lg" onClick={goToNextStep}>
            Continue to Evaluation
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
              <path d="M7.5 15l5-5-5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        )}

        {(isFailed || isCancelled) && (
          <button className="btn btn-primary" onClick={handleStartTraining}>
            Retry Training
          </button>
        )}
      </div>
    </div>
  );
}
