/**
 * ModelConfigStep Component
 *
 * Third step: Configure the model and training hyperparameters.
 */

import { useFineTuning } from '../../../contexts/FineTuningContext';
import type { BaseModel, BaseModelId } from '../../../types/finetuning';

const BASE_MODELS: BaseModel[] = [
  {
    id: 'chemberta-77m-mtr',
    name: 'ChemBERTa-77M-MTR',
    description: 'Pre-trained on 77M molecules with multi-task regression head',
    parameters: '77M',
    recommended: true,
    bestFor: ['IC50', 'Ki', 'EC50', 'property prediction'],
  },
  {
    id: 'chemberta-77m-mlm',
    name: 'ChemBERTa-77M-MLM',
    description: 'Masked language model for general molecular understanding',
    parameters: '77M',
    bestFor: ['transfer learning', 'molecular embeddings'],
  },
  {
    id: 'molbert-100m',
    name: 'MolBERT-100M',
    description: 'Larger model for complex structure-activity relationships',
    parameters: '100M',
    bestFor: ['complex SAR', 'multi-target prediction'],
  },
];

export function ModelConfigStep() {
  const {
    dataset,
    baseModel,
    setBaseModel,
    hyperparameters,
    updateHyperparameter,
    goToNextStep,
    goToPrevStep,
  } = useFineTuning();

  // Estimate training time and cost
  const estimatedEpochTime = dataset
    ? Math.ceil((dataset.validCount / hyperparameters.batchSize) * 0.1) // ~0.1s per step
    : 60;
  const estimatedTotalTime = estimatedEpochTime * hyperparameters.epochs;
  const estimatedCost = (estimatedTotalTime / 3600) * 6; // $6/hr

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
          <h1 className="content-title">Model Configuration</h1>
          <p className="content-subtitle">
            Select the base model and configure training hyperparameters.
          </p>
        </div>
      </div>

      {/* Base Model Selection */}
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Base Model</h3>
        </div>
        <div className="model-selection">
          {BASE_MODELS.map((model) => (
            <label
              key={model.id}
              className={`model-option ${baseModel === model.id ? 'selected' : ''}`}
            >
              <input
                type="radio"
                name="baseModel"
                value={model.id}
                checked={baseModel === model.id}
                onChange={() => setBaseModel(model.id as BaseModelId)}
              />
              <div className="model-option-content">
                <div className="model-option-header">
                  <span className="model-option-name">{model.name}</span>
                  {model.recommended && (
                    <span className="model-option-badge recommended">Recommended</span>
                  )}
                  <span className="model-option-badge params">{model.parameters}</span>
                </div>
                <p className="model-option-description">{model.description}</p>
                <div className="model-option-tags">
                  {model.bestFor.map((tag) => (
                    <span key={tag} className="model-option-tag">
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            </label>
          ))}
        </div>
      </div>

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
              <option value={2e-5}>2e-5 (Aggressive)</option>
              <option value={5e-5}>5e-5 (Very Aggressive)</option>
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

      {/* Nebius Serverless Compute */}
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
            <h3 className="card-title">Nebius Serverless Compute</h3>
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
            <div className="estimate-item">
              <span className="estimate-icon">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <path d="M8 2v12M4 6l4-4 4 4M4 10l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </span>
              <span className="estimate-label">Est. Cost</span>
              <span className="estimate-value">${estimatedCost.toFixed(2)}</span>
            </div>
          </div>

          <div className="serverless-note">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
              <circle cx="7" cy="7" r="6" stroke="currentColor" strokeWidth="1.5" />
              <path d="M7 4v3M7 9h.01" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
            <span>Pay only for GPU time used. No idle costs. Cold start: ~7s.</span>
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
