/**
 * ModelConfigStep Component
 *
 * Fourth step: Configure training hyperparameters.
 * Model is already selected in step 1 - shows summary and hyperparams.
 */

import { useFineTuning } from '../../../contexts/FineTuningContext';

export function ModelConfigStep() {
  const {
    dataset,
    selectedModel,
    hyperparameters,
    updateHyperparameter,
    goToNextStep,
    goToPrevStep,
  } = useFineTuning();

  // Estimate training time
  const estimatedEpochTime = dataset
    ? Math.ceil((dataset.validCount / hyperparameters.batchSize) * 0.1) // ~0.1s per step
    : 60;
  const estimatedTotalTime = estimatedEpochTime * hyperparameters.epochs;

  const formatTime = (seconds: number) => {
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${minutes}m ${secs}s`;
  };

  return (
    <div className="step-content">
      <div className="content-header">
        <div>
          <h1 className="content-title">Training Configuration</h1>
          <p className="content-subtitle">
            Configure hyperparameters for fine-tuning{selectedModel ? ` ${selectedModel.name}` : ''}.
          </p>
        </div>
      </div>

      {/* Selected Model Summary */}
      {selectedModel && (
        <div className="card model-summary-card">
          <div className="card-header">
            <h3 className="card-title">Base Model</h3>
            <span className="card-badge">{selectedModel.params} parameters</span>
          </div>
          <div className="model-summary-details">
            <div className="model-summary-item">
              <span className="model-summary-label">Model</span>
              <span className="model-summary-value">{selectedModel.name}</span>
            </div>
            <div className="model-summary-item">
              <span className="model-summary-label">Provider</span>
              <span className="model-summary-value">{selectedModel.provider}</span>
            </div>
            <div className="model-summary-item">
              <span className="model-summary-label">Modality</span>
              <span className="model-summary-value" style={{ textTransform: 'capitalize' }}>{selectedModel.modality}</span>
            </div>
            <div className="model-summary-item">
              <span className="model-summary-label">Task</span>
              <span className="model-summary-value" style={{ textTransform: 'capitalize' }}>{selectedModel.taskType}</span>
            </div>
          </div>
        </div>
      )}

      {/* Hyperparameters */}
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Training Parameters</h3>
          <span className="card-badge">
            Auto-configured for {dataset?.validCount.toLocaleString()} samples
          </span>
        </div>
        <div className="hyperparameters-grid">
          <div className="hyperparam-item">
            <label className="hyperparam-label">Epochs</label>
            <input
              type="number"
              className="hyperparam-input"
              value={hyperparameters.epochs}
              onChange={(e) => updateHyperparameter('epochs', parseInt(e.target.value) || 10)}
              min={1}
              max={100}
            />
            <span className="hyperparam-hint">Number of training passes</span>
          </div>

          <div className="hyperparam-item">
            <label className="hyperparam-label">Batch Size</label>
            <select
              className="hyperparam-input"
              value={hyperparameters.batchSize}
              onChange={(e) => updateHyperparameter('batchSize', parseInt(e.target.value))}
            >
              <option value={4}>4</option>
              <option value={8}>8</option>
              <option value={16}>16</option>
              <option value={32}>32</option>
              <option value={64}>64</option>
              <option value={128}>128</option>
            </select>
            <span className="hyperparam-hint">Samples per training step</span>
          </div>

          <div className="hyperparam-item">
            <label className="hyperparam-label">Learning Rate</label>
            <select
              className="hyperparam-input"
              value={hyperparameters.learningRate}
              onChange={(e) => updateHyperparameter('learningRate', parseFloat(e.target.value))}
            >
              <option value={1e-6}>1e-6 (Very Conservative)</option>
              <option value={5e-6}>5e-6 (Conservative)</option>
              <option value={1e-5}>1e-5 (Default)</option>
              <option value={2e-5}>2e-5 (Moderate)</option>
              <option value={5e-5}>5e-5 (Aggressive)</option>
              <option value={1e-4}>1e-4 (Very Aggressive)</option>
            </select>
            <span className="hyperparam-hint">Step size for optimization</span>
          </div>

          <div className="hyperparam-item">
            <label className="hyperparam-label">Weight Decay</label>
            <input
              type="number"
              className="hyperparam-input"
              value={hyperparameters.weightDecay}
              onChange={(e) => updateHyperparameter('weightDecay', parseFloat(e.target.value) || 0.01)}
              min={0}
              max={1}
              step={0.001}
            />
            <span className="hyperparam-hint">L2 regularization strength</span>
          </div>

          <div className="hyperparam-item">
            <label className="hyperparam-label">Warmup Steps</label>
            <input
              type="number"
              className="hyperparam-input"
              value={hyperparameters.warmupSteps}
              onChange={(e) => updateHyperparameter('warmupSteps', parseInt(e.target.value) || 100)}
              min={0}
              max={1000}
            />
            <span className="hyperparam-hint">LR warmup period</span>
          </div>

          <div className="hyperparam-item">
            <label className="hyperparam-label">Early Stopping</label>
            <div className="hyperparam-toggle-row">
              <label className="toggle-switch">
                <input
                  type="checkbox"
                  checked={hyperparameters.earlyStoppingEnabled}
                  onChange={(e) => updateHyperparameter('earlyStoppingEnabled', e.target.checked)}
                />
                <span className="toggle-slider" />
              </label>
              {hyperparameters.earlyStoppingEnabled && (
                <input
                  type="number"
                  className="hyperparam-input-small"
                  value={hyperparameters.earlyStoppingPatience}
                  onChange={(e) =>
                    updateHyperparameter('earlyStoppingPatience', parseInt(e.target.value) || 3)
                  }
                  min={1}
                  max={20}
                  placeholder="Patience"
                />
              )}
            </div>
            <span className="hyperparam-hint">Stop if validation doesn't improve</span>
          </div>
        </div>
      </div>

      {/* Nebius Jobs */}
      <div className="card serverless-card">
        <div className="card-header">
          <div className="serverless-header">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
              <path
                d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <h3 className="card-title">Nebius Jobs</h3>
          </div>
        </div>
        <div className="serverless-info">
          <div className="serverless-specs">
            <div className="serverless-spec">
              <span className="serverless-spec-label">GPU</span>
              <span className="serverless-spec-value">NVIDIA H200 SXM</span>
            </div>
            <div className="serverless-spec">
              <span className="serverless-spec-label">Memory</span>
              <span className="serverless-spec-value">80 GB HBM3</span>
            </div>
            <div className="serverless-spec">
              <span className="serverless-spec-label">Preset</span>
              <span className="serverless-spec-value">1gpu-16vcpu-200gb</span>
            </div>
          </div>

          <div className="serverless-estimates">
            <div className="estimate-item">
              <span className="estimate-icon">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.5" />
                  <path d="M8 4v4l2 1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
              </span>
              <span className="estimate-label">Est. Time</span>
              <span className="estimate-value">{formatTime(estimatedTotalTime)}</span>
            </div>
          </div>

          <div className="serverless-note">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <circle cx="7" cy="7" r="6" stroke="currentColor" strokeWidth="1.5" />
              <path d="M7 4v3M7 9h.01" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
            <span>Pay only for GPU time used. Cold start: ~7s.</span>
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="step-actions">
        <button className="btn btn-ghost" onClick={goToPrevStep}>
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M12.5 15l-5-5 5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Back
        </button>
        <button className="btn btn-primary btn-lg" onClick={goToNextStep}>
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M4 4l12 6-12 6V4z" fill="currentColor" />
          </svg>
          Start Training
        </button>
      </div>
    </div>
  );
}
