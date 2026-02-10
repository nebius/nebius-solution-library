/**
 * ModelSelectionStep Component
 *
 * First step: Select a base model for fine-tuning.
 * Two tabs: Molecular Models (SMILES-based) and Protein Models (sequence-based).
 */

import { useState } from 'react';
import { useFineTuning } from '../../../contexts/FineTuningContext';
import { getModelsByModality } from '../../../data/modelRegistry';
import type { ModelModality, ModelInfo } from '../../../types/finetuning';

export function ModelSelectionStep() {
  const { selectedModel, setSelectedModel, goToNextStep } = useFineTuning();
  const [activeTab, setActiveTab] = useState<ModelModality>('molecular');

  const molecularModels = getModelsByModality('molecular');
  const proteinModels = getModelsByModality('protein');
  const models = activeTab === 'molecular' ? molecularModels : proteinModels;

  const handleSelectModel = (model: ModelInfo) => {
    setSelectedModel(model);
  };

  const handleContinue = () => {
    if (selectedModel) {
      goToNextStep();
    }
  };

  return (
    <div className="step-content">
      <div className="content-header">
        <div>
          <h1 className="content-title">Select Base Model</h1>
          <p className="content-subtitle">
            Choose an open-source model to fine-tune on your data. Models are organized by input modality.
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div className="model-tabs">
        <button
          className={`model-tab ${activeTab === 'molecular' ? 'active' : ''}`}
          onClick={() => setActiveTab('molecular')}
        >
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
            <circle cx="9" cy="5" r="2" stroke="currentColor" strokeWidth="1.5" />
            <circle cx="4" cy="13" r="2" stroke="currentColor" strokeWidth="1.5" />
            <circle cx="14" cy="13" r="2" stroke="currentColor" strokeWidth="1.5" />
            <path d="M7.5 6.5L5.5 11.5M10.5 6.5L12.5 11.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
          Molecular Models
          <span className="model-tab-count">{molecularModels.length}</span>
        </button>
        <button
          className={`model-tab ${activeTab === 'protein' ? 'active' : ''}`}
          onClick={() => setActiveTab('protein')}
        >
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
            <path d="M3 9c0-3 2-6 6-6s6 3 6 6-2 6-6 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            <path d="M6 6c1 2 3 3 5 3M5 12c1-1 3-2 5-2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
          Protein Models
          <span className="model-tab-count">{proteinModels.length}</span>
        </button>
      </div>

      {/* Model Grid */}
      <div className="model-grid">
        {models.map((model) => (
          <button
            key={model.id}
            className={`model-card ${selectedModel?.id === model.id ? 'selected' : ''}`}
            onClick={() => handleSelectModel(model)}
          >
            <div className="model-card-header">
              <div className="model-card-title-row">
                <span className="model-card-name">{model.name}</span>
                <span className="model-card-params">{model.params}</span>
              </div>
              <span className="model-card-provider">{model.provider}</span>
            </div>
            <p className="model-card-description">{model.description}</p>
            <div className="model-card-footer">
              <span className={`model-card-task ${model.taskType}`}>
                {model.taskType === 'regression' ? 'Regression' : 'Classification'}
              </span>
              <div className="model-card-links">
                <a
                  href={model.paperUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={(e) => e.stopPropagation()}
                  className="model-card-link"
                  title="Paper"
                >
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                    <path d="M3 2h5l3 3v7a1 1 0 01-1 1H3a1 1 0 01-1-1V3a1 1 0 011-1z" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
                    <path d="M8 2v3h3" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </a>
                <a
                  href={model.huggingFaceUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={(e) => e.stopPropagation()}
                  className="model-card-link"
                  title="Hugging Face"
                >
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                    <circle cx="7" cy="7" r="6" stroke="currentColor" strokeWidth="1.2" />
                    <path d="M4 6v1M10 6v1M5 9.5s.8 1 2 1 2-1 2-1" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
                  </svg>
                </a>
              </div>
            </div>
            {selectedModel?.id === model.id && (
              <div className="model-card-check">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <path d="M3 8l3 3 7-7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
            )}
          </button>
        ))}
      </div>

      {/* Selected Model Summary */}
      {selectedModel && (
        <div className="card model-summary-card">
          <div className="card-header">
            <h3 className="card-title">Selected: {selectedModel.name}</h3>
            <span className="card-badge">{selectedModel.params} parameters</span>
          </div>
          <div className="model-summary-details">
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
            <div className="model-summary-item">
              <span className="model-summary-label">Default LR</span>
              <span className="model-summary-value">{selectedModel.defaultHyperparameters.learningRate}</span>
            </div>
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="step-actions">
        <div />
        <button
          className="btn btn-primary btn-lg"
          onClick={handleContinue}
          disabled={!selectedModel}
        >
          Continue to Data Selection
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M7.5 15l5-5-5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>
    </div>
  );
}
