/**
 * ModelSelectionStep Component
 *
 * First step: Select a base model for fine-tuning.
 * Two tabs: Molecular Models (SMILES-based) and Protein Models (sequence-based).
 * Includes "Help Me Choose" AI assistant powered by Nemotron.
 */

import { useState, useCallback } from 'react';
import { useFineTuning } from '../../../contexts/FineTuningContext';
import { useGatewayUrl } from '../../../contexts/GatewayContext';
import { getModelsByModality, MODEL_REGISTRY, getModelById } from '../../../data/modelRegistry';
import { streamChat } from '../../../services/nimApi';
import type { ModelModality, ModelInfo } from '../../../types/finetuning';

const EXAMPLE_PROBLEM = `I want to predict binding affinity of small molecules against the COX-2 enzyme for anti-inflammatory drug discovery. My dataset has ~3000 compounds with IC50 values.`;

/** Build a compact model catalog string for the LLM prompt */
function buildModelCatalog(): string {
  const molecular = MODEL_REGISTRY.filter((m) => m.modality === 'molecular');
  const protein = MODEL_REGISTRY.filter((m) => m.modality === 'protein');

  const fmt = (m: ModelInfo) => `- ${m.name} (id: ${m.id}): ${m.params} params, ${m.provider}. ${m.description}`;

  return [
    'MOLECULAR MODELS (SMILES input, regression):',
    ...molecular.map(fmt),
    '',
    'PROTEIN MODELS (sequence input, classification):',
    ...protein.map(fmt),
  ].join('\n');
}

const MODEL_ADVISOR_SYSTEM = `You are a machine learning advisor for drug discovery. The user will describe their problem and you must recommend the best base model to fine-tune from the available catalog.

Available models:
${buildModelCatalog()}

Rules:
- Recommend 1-2 best models from the catalog above
- Mention the model name exactly as shown (e.g., "ChemBERTa-77M-MTR")
- Explain briefly why (2-3 sentences max per model)
- If the best possible model is NOT in the catalog, note what would be better
- Keep it short and actionable
- Do not use tables`;

export function ModelSelectionStep() {
  const { selectedModel, setSelectedModel, goToNextStep } = useFineTuning();
  const gatewayUrl = useGatewayUrl();
  const [activeTab, setActiveTab] = useState<ModelModality>('molecular');

  // Help Me Choose state
  const [showHelper, setShowHelper] = useState(true);
  const [problemText, setProblemText] = useState(EXAMPLE_PROBLEM);
  const [isRecommending, setIsRecommending] = useState(false);
  const [recommendation, setRecommendation] = useState('');
  const [recommendError, setRecommendError] = useState<string | null>(null);

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

  /** Find model IDs mentioned in the recommendation text */
  const getRecommendedModels = useCallback((): ModelInfo[] => {
    if (!recommendation) return [];
    const found: ModelInfo[] = [];
    for (const model of MODEL_REGISTRY) {
      if (recommendation.includes(model.name) || recommendation.includes(model.id)) {
        found.push(model);
      }
    }
    return found;
  }, [recommendation]);

  const handleGetRecommendation = useCallback(async () => {
    if (!gatewayUrl || !problemText.trim()) return;

    setIsRecommending(true);
    setRecommendation('');
    setRecommendError(null);

    try {
      const messages = [
        { role: 'system' as const, content: MODEL_ADVISOR_SYSTEM },
        { role: 'user' as const, content: problemText.trim() },
      ];

      let content = '';

      for await (const chunk of streamChat(gatewayUrl, messages, { maxTokens: 8192, temperature: 0.7 })) {
        if (chunk.type === 'content') {
          content += chunk.text;
          setRecommendation(content.trim());
        }
        // Skip reasoning chunks — don't display
      }

      // If no content was produced, try to extract from reasoning
      if (!content) {
        setRecommendError('Model did not produce a recommendation. Please try again.');
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to get recommendation';
      setRecommendError(message);
    } finally {
      setIsRecommending(false);
    }
  }, [gatewayUrl, problemText]);

  const handleUseModel = useCallback((modelId: string) => {
    const model = getModelById(modelId);
    if (model) {
      setSelectedModel(model);
      // Switch tab to the model's modality
      setActiveTab(model.modality);
    }
  }, [setSelectedModel]);

  const recommendedModels = getRecommendedModels();

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

      {/* Help Me Choose Section */}
      <div className="card">
        <div className="card-header" style={{ cursor: 'pointer' }} onClick={() => setShowHelper(!showHelper)}>
          <h3 className="card-title" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
              <circle cx="9" cy="9" r="7" stroke="currentColor" strokeWidth="1.5" />
              <path d="M7 7a2 2 0 1 1 2 2v1.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              <circle cx="9" cy="13" r="0.75" fill="currentColor" />
            </svg>
            Help Me Choose
          </h3>
          <svg
            width="16" height="16" viewBox="0 0 16 16" fill="none"
            style={{ transform: showHelper ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }}
          >
            <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>

        {showHelper && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            <p className="content-subtitle" style={{ margin: 0 }}>
              Describe your problem and let AI recommend the best base model.
            </p>
            <textarea
              className="query-textarea"
              value={problemText}
              onChange={(e) => setProblemText(e.target.value)}
              rows={3}
              placeholder="Describe your drug discovery problem..."
              disabled={isRecommending}
              style={{ resize: 'vertical', minHeight: '60px' }}
            />
            <div>
              <button
                className="btn btn-outline"
                onClick={handleGetRecommendation}
                disabled={!gatewayUrl || !problemText.trim() || isRecommending}
              >
                {isRecommending ? (
                  <>
                    <span className="spinner spinner-sm" />
                    Analyzing...
                  </>
                ) : (
                  <>
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                      <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.5" />
                      <path d="M8 5v3l2 1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                    </svg>
                    Get Recommendation
                  </>
                )}
              </button>
              {!gatewayUrl && (
                <span style={{ marginLeft: '0.75rem', fontSize: '0.8rem', opacity: 0.6 }}>
                  Enter NIM Gateway URL first
                </span>
              )}
            </div>

            {recommendation && (
              <div className="seed-response" style={{ marginTop: '0.25rem' }}>
                <div className="seed-response-text" style={{ whiteSpace: 'pre-wrap' }}>{recommendation}</div>

                {recommendedModels.length > 0 && (
                  <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginTop: '0.75rem' }}>
                    {recommendedModels.map((model) => (
                      <button
                        key={model.id}
                        className={`btn ${selectedModel?.id === model.id ? 'btn-primary' : 'btn-outline'} btn-sm`}
                        onClick={() => handleUseModel(model.id)}
                      >
                        {selectedModel?.id === model.id ? (
                          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                            <path d="M2 7l3 3 7-7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                          </svg>
                        ) : null}
                        Use {model.name}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {recommendError && <p className="seed-error">{recommendError}</p>}
          </div>
        )}
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
