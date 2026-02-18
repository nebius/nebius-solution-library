import { useState, useCallback, useMemo, useEffect } from 'react';
import { formatDuration } from '../../hooks/useProgressTracker';
import { STRUCTURE_MODELS } from '../../data/endpoints';
import {
  type StructurePredictionResult,
  type ParallelPredictionResult,
  type ModelRequestBody,
  getAllModelRequests,
  predictWithCustomBody,
} from '../../services/structurePrediction';
import {
  searchMsa,
  buildOpenFold3RequestWithMsa,
  buildOpenFold2RequestWithMsa,
  type MsaSearchResult,
} from '../../services/msaSearch';
import { buildNimUrl } from '../../services/nimApi';
import { StructureViewer } from '../StructureViewer';

import { getNumCopiesFromOligomericState } from '../../data/drugs';

interface ProteinInfo {
  accession: string;
  name: string;
  organism: string;
  sequence: string;
  length: number;
}

interface StructureStepProps {
  proteinInfo: ProteinInfo | null;
  gatewayUrl: string;
  selectedModel: string | null;
  onSelectModel: (modelId: string) => void;
  onStructureResult: (result: StructurePredictionResult) => void;
  onContinue: () => void;
  onBack: () => void;
  oligomericState?: 'monomer' | 'homodimer' | 'homotrimer' | 'homotetramer';
}

type ModelId = 'openfold3' | 'boltz2' | 'openfold2';
const ALL_MODELS: ModelId[] = ['boltz2', 'openfold3', 'openfold2'];

export function StructureStep({
  proteinInfo,
  gatewayUrl,
  onStructureResult,
  onContinue,
  onBack,
  oligomericState,
}: StructureStepProps) {
  const [isProcessing, setIsProcessing] = useState(false);
  const [runningModels, setRunningModels] = useState<Set<ModelId>>(new Set());
  const [results, setResults] = useState<ParallelPredictionResult[]>([]);
  const [predictionStartTime, setPredictionStartTime] = useState<number>(0);
  const [elapsedTime, setElapsedTime] = useState<number>(0);
  const [selectedResultModel, setSelectedResultModel] = useState<ModelId | null>(null);
  const [showQueryEditor, setShowQueryEditor] = useState(false);
  const [expandedQueries, setExpandedQueries] = useState<Set<ModelId>>(new Set());
  const [editedRequests, setEditedRequests] = useState<Record<ModelId, string>>({} as Record<ModelId, string>);
  const [queryErrors, setQueryErrors] = useState<Record<ModelId, string | null>>({} as Record<ModelId, string | null>);
  const [enabledModels, setEnabledModels] = useState<Set<ModelId>>(new Set(ALL_MODELS));

  // MSA Search state
  const [useMsaSearch, setUseMsaSearch] = useState(false);
  const [isSearchingMsa, setIsSearchingMsa] = useState(false);
  const [msaResult, setMsaResult] = useState<MsaSearchResult | null>(null);
  const [msaError, setMsaError] = useState<string | null>(null);

  // Build initial requests when protein info changes (or MSA result changes)
  const initialRequests = useMemo(() => {
    if (!proteinInfo || !gatewayUrl) return [];

    const baseUrl = gatewayUrl;

    // Get number of copies based on oligomeric state (for homodimers, etc.)
    const numCopies = getNumCopiesFromOligomericState(oligomericState);

    // If we have MSA result, use it for OpenFold2 and OpenFold3
    if (msaResult) {
      return [
        {
          modelId: 'boltz2' as const,
          endpoint: buildNimUrl(baseUrl, 8001, '/biology/mit/boltz2/predict'),
          body: {
            polymers: [{ molecule_type: 'protein', sequence: proteinInfo.sequence, cyclic: false }],
            recycling_steps: 3,
            sampling_steps: 50,
            diffusion_samples: 1,
            step_scale: 1.638,
            output_format: 'mmcif',
          },
        },
        {
          modelId: 'openfold3' as const,
          endpoint: buildNimUrl(baseUrl, 8000, '/biology/openfold/openfold3/predict'),
          body: buildOpenFold3RequestWithMsa(proteinInfo.sequence, msaResult.alignment, numCopies),
        },
        {
          modelId: 'openfold2' as const,
          endpoint: buildNimUrl(baseUrl, 8004, '/biology/openfold/openfold2/predict-structure-from-msa-and-template'),
          body: buildOpenFold2RequestWithMsa(proteinInfo.sequence, msaResult.alignment),
        },
      ];
    }

    return getAllModelRequests(baseUrl, proteinInfo.sequence, numCopies);
  }, [proteinInfo, gatewayUrl, msaResult, oligomericState]);

  // Initialize edited requests when initial requests change
  useEffect(() => {
    if (initialRequests.length > 0) {
      const edited: Record<ModelId, string> = {} as Record<ModelId, string>;
      initialRequests.forEach((req) => {
        edited[req.modelId] = JSON.stringify(req.body, null, 2);
      });
      setEditedRequests(edited);
      setQueryErrors({} as Record<ModelId, string | null>);
    }
  }, [initialRequests]);

  const handleToggleModel = useCallback((modelId: ModelId) => {
    setEnabledModels((prev) => {
      const next = new Set(prev);
      if (next.has(modelId)) {
        next.delete(modelId);
      } else {
        next.add(modelId);
      }
      return next;
    });
  }, []);

  const handleSelectAllModels = useCallback(() => {
    setEnabledModels(new Set(ALL_MODELS));
  }, []);

  const handleToggleQuery = useCallback((modelId: ModelId) => {
    setExpandedQueries((prev) => {
      const next = new Set(prev);
      if (next.has(modelId)) {
        next.delete(modelId);
      } else {
        next.add(modelId);
      }
      return next;
    });
  }, []);

  const handleQueryChange = useCallback((modelId: ModelId, value: string) => {
    setEditedRequests((prev) => ({ ...prev, [modelId]: value }));
    // Validate JSON
    try {
      JSON.parse(value);
      setQueryErrors((prev) => ({ ...prev, [modelId]: null }));
    } catch {
      setQueryErrors((prev) => ({ ...prev, [modelId]: 'Invalid JSON' }));
    }
  }, []);

  // Update elapsed time while processing
  useEffect(() => {
    if (!isProcessing || predictionStartTime === 0) return;

    const interval = setInterval(() => {
      setElapsedTime(Date.now() - predictionStartTime);
    }, 1000);

    return () => clearInterval(interval);
  }, [isProcessing, predictionStartTime]);

  const handleRunAllPredictions = useCallback(async () => {
    if (!proteinInfo || !gatewayUrl || enabledModels.size === 0) return;

    // Check for JSON errors in enabled models only
    const hasErrors = Array.from(enabledModels).some((modelId) => queryErrors[modelId]);
    if (hasErrors) {
      return;
    }

    const startTime = Date.now();
    setPredictionStartTime(startTime);
    setElapsedTime(0);
    setIsProcessing(true);
    setResults([]);
    setSelectedResultModel(null);
    setRunningModels(new Set(enabledModels));

    // Build requests from edited JSON, only for enabled models
    const requests: ModelRequestBody[] = initialRequests
      .filter((req) => enabledModels.has(req.modelId))
      .map((req) => {
        try {
          const editedBody = JSON.parse(editedRequests[req.modelId] || '{}');
          return { ...req, body: editedBody };
        } catch {
          return req;
        }
      });

    // Initialize results with pending status for all enabled models
    const initialResults: ParallelPredictionResult[] = requests.map((req) => ({
      modelId: req.modelId,
      status: 'pending' as const,
    }));
    setResults(initialResults);

    // Run each model and update results as they complete
    const promises = requests.map(async (req) => {
      const startTime = Date.now();
      try {
        const result = await predictWithCustomBody(req.endpoint, req.body, req.modelId);
        const elapsedTime = Date.now() - startTime;

        // Update this model's result
        setResults((prev) =>
          prev.map((r) =>
            r.modelId === req.modelId
              ? { modelId: req.modelId, status: 'success' as const, result, elapsedTime }
              : r
          )
        );

        // Remove from running models
        setRunningModels((prev) => {
          const next = new Set(prev);
          next.delete(req.modelId);
          return next;
        });

        return { modelId: req.modelId, success: true, result };
      } catch (error) {
        const elapsedTime = Date.now() - startTime;
        const errorMessage = error instanceof Error ? error.message : 'Unknown error';

        // Update this model's result with error
        setResults((prev) =>
          prev.map((r) =>
            r.modelId === req.modelId
              ? { modelId: req.modelId, status: 'error' as const, error: errorMessage, elapsedTime }
              : r
          )
        );

        // Remove from running models
        setRunningModels((prev) => {
          const next = new Set(prev);
          next.delete(req.modelId);
          return next;
        });

        return { modelId: req.modelId, success: false, error: errorMessage };
      }
    });

    // Wait for all to complete
    const allResults = await Promise.all(promises);

    // Auto-select the best result (highest confidence)
    const successResults = allResults.filter((r) => r.success && r.result);
    if (successResults.length > 0) {
      const best = successResults.reduce((a, b) =>
        (a.result?.confidenceScore ?? 0) > (b.result?.confidenceScore ?? 0) ? a : b
      );
      setSelectedResultModel(best.modelId);
    }

    setIsProcessing(false);
  }, [proteinInfo, gatewayUrl, initialRequests, editedRequests, queryErrors, enabledModels]);

  const handleSelectResult = useCallback((modelId: ModelId) => {
    setSelectedResultModel(modelId);
  }, []);

  // MSA Search handler
  const handleMsaSearch = useCallback(async () => {
    if (!proteinInfo || !gatewayUrl) return;

    setIsSearchingMsa(true);
    setMsaError(null);
    setMsaResult(null);

    try {
      const result = await searchMsa(gatewayUrl, proteinInfo.sequence);
      setMsaResult(result);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'MSA search failed';
      setMsaError(message);
    } finally {
      setIsSearchingMsa(false);
    }
  }, [proteinInfo, gatewayUrl]);

  // Clear MSA result when toggle is turned off
  const handleMsaToggle = useCallback((enabled: boolean) => {
    setUseMsaSearch(enabled);
    if (!enabled) {
      setMsaResult(null);
      setMsaError(null);
    }
  }, []);

  const handleContinue = useCallback(() => {
    if (!selectedResultModel) return;
    const selected = results.find((r) => r.modelId === selectedResultModel);
    if (selected?.result) {
      onStructureResult(selected.result);
      onContinue();
    }
  }, [selectedResultModel, results, onStructureResult, onContinue]);

  const handleDownloadStructure = useCallback((result: StructurePredictionResult) => {
    const blob = new Blob([result.structure], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const ext = result.format === 'pdb' ? 'pdb' : 'cif';
    a.download = `${proteinInfo?.accession || 'structure'}_${result.modelUsed}.${ext}`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, [proteinInfo]);

  const formatElapsedTime = (ms?: number) => {
    if (!ms) return '-';
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  };

  const getScoreColor = (score: number, max: number = 1) => {
    const normalized = score / max;
    if (normalized >= 0.7) return 'score-high';
    if (normalized >= 0.4) return 'score-medium';
    return 'score-low';
  };

  if (!proteinInfo) {
    return (
      <div className="step-content">
        <div className="content-header">
          <div>
            <h1 className="content-title">Structure Prediction</h1>
            <p className="content-subtitle">Please fetch a protein sequence first.</p>
          </div>
        </div>
        <div className="step-actions">
          <button className="btn btn-ghost" onClick={onBack}>
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
              <path d="M12.5 15l-5-5 5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            Back
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="step-content">
      <div className="content-header">
        <div>
          <h1 className="content-title">Structure Prediction</h1>
          <p className="content-subtitle">
            Run all models in parallel to compare results and select the best prediction.
          </p>
        </div>
      </div>

      {/* Target Protein Info */}
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Target Protein</h3>
          <span className="card-badge">{proteinInfo.accession}</span>
        </div>
        <div className="protein-info">
          <div className="protein-info-row">
            <span className="protein-info-label">Name</span>
            <span className="protein-info-value">{proteinInfo.name}</span>
          </div>
          <div className="protein-info-row">
            <span className="protein-info-label">Organism</span>
            <span className="protein-info-value">{proteinInfo.organism}</span>
          </div>
          <div className="protein-info-row">
            <span className="protein-info-label">Length</span>
            <span className="protein-info-value">{proteinInfo.length} residues</span>
          </div>
        </div>
        <div className="sequence-display">
          <div className="sequence-header">
            <span className="sequence-label">Amino Acid Sequence</span>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => navigator.clipboard.writeText(proteinInfo.sequence)}
              title="Copy sequence"
            >
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <rect x="4" y="4" width="8" height="8" rx="1" stroke="currentColor" strokeWidth="1.5" />
                <path d="M2 10V3a1 1 0 0 1 1-1h7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
              Copy
            </button>
          </div>
          <div className="sequence-content">
            <code className="sequence-text">
              {proteinInfo.sequence.match(/.{1,60}/g)?.map((chunk, i) => (
                <div key={i} className="sequence-line">
                  <span className="sequence-position">{i * 60 + 1}</span>
                  <span className="sequence-chunk">{chunk}</span>
                </div>
              ))}
            </code>
          </div>
        </div>
      </div>

      {/* MSA Search (Optional) */}
      <div className="card">
        <div className="card-header">
          <div className="msa-header-content">
            <h3 className="card-title">MSA Search</h3>
            <span className="optional-badge">Optional</span>
          </div>
          <label className="toggle-switch">
            <input
              type="checkbox"
              checked={useMsaSearch}
              onChange={(e) => handleMsaToggle(e.target.checked)}
              disabled={isProcessing || isSearchingMsa}
            />
            <span className="toggle-slider" />
          </label>
        </div>

        {!useMsaSearch && (
          <p className="msa-description">
            Enable MSA (Multiple Sequence Alignment) search to find homologous sequences.
            This can significantly improve prediction accuracy for OpenFold2 and OpenFold3.
          </p>
        )}

        {useMsaSearch && (
          <div className="msa-search-content">
            {!msaResult && !isSearchingMsa && !msaError && (
              <div className="msa-action">
                <p className="msa-info">
                  Search UniRef90 database for homologous sequences. This may take a few moments.
                </p>
                <button
                  className="btn btn-primary"
                  onClick={handleMsaSearch}
                  disabled={!gatewayUrl}
                >
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <circle cx="7" cy="7" r="5" stroke="currentColor" strokeWidth="1.5" />
                    <path d="M11 11l3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                  </svg>
                  Search for Homologs
                </button>
              </div>
            )}

            {isSearchingMsa && (
              <div className="msa-searching">
                <span className="spinner" />
                <span>Searching UniRef90 database...</span>
              </div>
            )}

            {msaError && (
              <div className="msa-error">
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.5" />
                  <path d="M8 5v4M8 11v.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
                <span>{msaError}</span>
                <button className="btn btn-ghost btn-sm" onClick={handleMsaSearch}>
                  Retry
                </button>
              </div>
            )}

            {msaResult && (
              <div className="msa-result">
                <div className="msa-result-stats">
                  <div className="msa-stat">
                    <span className="msa-stat-value">{msaResult.numSequences}</span>
                    <span className="msa-stat-label">Homologs Found</span>
                  </div>
                  <div className="msa-stat">
                    <span className="msa-stat-value">{msaResult.queryLength}</span>
                    <span className="msa-stat-label">Query Length</span>
                  </div>
                  <div className="msa-stat">
                    <span className="msa-stat-value">{msaResult.format.toUpperCase()}</span>
                    <span className="msa-stat-label">Format</span>
                  </div>
                </div>
                <div className="msa-success-badge">
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                    <path d="M2 7l3 3 7-7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  MSA will be used for OpenFold2 and OpenFold3 predictions
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Model Selection */}
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Select Models to Run</h3>
          <button
            className="btn btn-ghost btn-sm"
            onClick={handleSelectAllModels}
            disabled={enabledModels.size === ALL_MODELS.length}
          >
            Select All
          </button>
        </div>
        <div className="model-selection-grid">
          {STRUCTURE_MODELS.map((model) => {
            const modelId = model.id as ModelId;
            const isEnabled = enabledModels.has(modelId);

            return (
              <label key={modelId} className={`model-checkbox-card ${isEnabled ? 'enabled' : ''}`}>
                <input
                  type="checkbox"
                  checked={isEnabled}
                  onChange={() => handleToggleModel(modelId)}
                  disabled={isProcessing}
                />
                <div className="model-checkbox-content">
                  <div className="model-checkbox-header">
                    <span className="model-checkbox-name">{model.name}</span>
                    <span className={`model-badge ${model.badge.toLowerCase()}`}>{model.badge}</span>
                  </div>
                  <p className="model-checkbox-description">{model.description}</p>
                </div>
              </label>
            );
          })}
        </div>
        {enabledModels.size === 0 && (
          <p className="model-selection-warning">Please select at least one model to run</p>
        )}
      </div>

      {/* Query Editor Toggle */}
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">API Requests</h3>
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => setShowQueryEditor(!showQueryEditor)}
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M12 2l2 2-8 8H4v-2l8-8z" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            {showQueryEditor ? 'Hide' : 'Edit'} Queries
          </button>
        </div>

        {showQueryEditor && (
          <div className="query-editor-container">
            {STRUCTURE_MODELS.map((model) => {
              const modelId = model.id as ModelId;
              const isExpanded = expandedQueries.has(modelId);
              const error = queryErrors[modelId];
              const request = initialRequests.find((r) => r.modelId === modelId);

              return (
                <div key={modelId} className="query-editor-item">
                  <button
                    className="query-editor-header"
                    onClick={() => handleToggleQuery(modelId)}
                  >
                    <div className="query-editor-title">
                      <svg
                        width="12"
                        height="12"
                        viewBox="0 0 12 12"
                        fill="none"
                        className={`chevron ${isExpanded ? 'expanded' : ''}`}
                      >
                        <path d="M4 2l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                      <span>{model.name}</span>
                      <span className={`model-badge ${model.badge.toLowerCase()}`}>{model.badge}</span>
                    </div>
                    {error && <span className="query-error-badge">Error</span>}
                  </button>

                  {isExpanded && (
                    <div className="query-editor-body">
                      <div className="query-endpoint">
                        <span className="query-endpoint-label">Endpoint:</span>
                        <code className="query-endpoint-value">{request?.endpoint}</code>
                      </div>
                      <textarea
                        className={`query-textarea ${error ? 'has-error' : ''}`}
                        value={editedRequests[modelId] || ''}
                        onChange={(e) => handleQueryChange(modelId, e.target.value)}
                        spellCheck={false}
                      />
                      {error && <p className="query-error-message">{error}</p>}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Run Button */}
      {results.length === 0 && !isProcessing && (
        <div className="card prediction-action-card">
          <div className="prediction-action-content">
            <button
              className="btn btn-primary btn-lg"
              onClick={handleRunAllPredictions}
              disabled={!gatewayUrl || enabledModels.size === 0 || Array.from(enabledModels).some((m) => queryErrors[m])}
            >
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <path d="M4 4l12 6-12 6V4z" fill="currentColor" />
              </svg>
              Run {enabledModels.size === 1 ? 'Selected Model' : `${enabledModels.size} Models in Parallel`}
            </button>
            {!gatewayUrl && (
              <p className="prediction-hint">Enter NIM Gateway URL to continue</p>
            )}
            <p className="prediction-info">
              {enabledModels.size === ALL_MODELS.length
                ? 'All structure prediction models will run simultaneously'
                : `Selected: ${Array.from(enabledModels).map((id) => STRUCTURE_MODELS.find((m) => m.id === id)?.name).join(', ')}`}
            </p>
          </div>
        </div>
      )}

      {/* Processing State */}
      {isProcessing && (
        <div className="card processing-card">
          <div className="processing-content">
            <div className="processing-spinner">
              <span className="spinner spinner-lg" />
            </div>
            <h3 className="processing-title">
              Running {enabledModels.size === 1 ? 'Model' : `${enabledModels.size} Models in Parallel`}
            </h3>
            <p className="processing-description">
              Predicting 3D structure for {proteinInfo.length} residues...
            </p>
            {/* Elapsed time display */}
            <div className="progress-eta" style={{ marginTop: 'var(--spacing-md)' }}>
              <span className="progress-elapsed">Elapsed: {formatDuration(elapsedTime)}</span>
            </div>
            <div className="parallel-indicators">
              {STRUCTURE_MODELS.filter((model) => enabledModels.has(model.id as ModelId)).map((model) => {
                const modelId = model.id as ModelId;
                const isRunning = runningModels.has(modelId);
                const result = results.find((r) => r.modelId === modelId);
                const isComplete = result?.status === 'success' || result?.status === 'error';

                return (
                  <div
                    key={model.id}
                    className={`parallel-indicator ${isComplete ? (result?.status === 'success' ? 'complete' : 'error') : ''}`}
                  >
                    {isRunning ? (
                      <span className="spinner spinner-sm" />
                    ) : result?.status === 'success' ? (
                      <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                        <path d="M2 7l3 3 7-7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    ) : result?.status === 'error' ? (
                      <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                        <path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                      </svg>
                    ) : (
                      <span className="spinner spinner-sm" />
                    )}
                    <span>{model.name}</span>
                    {result?.elapsedTime && (
                      <span className="parallel-indicator-time">
                        {formatElapsedTime(result.elapsedTime)}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* Results Comparison */}
      {results.length > 0 && (
        <div className="results-comparison">
          <h3 className="results-comparison-title">
            Results Comparison
            <span className="results-comparison-subtitle">Click on a structure to select it</span>
          </h3>

          <div className="structure-results-viewers">
            {results.map((result) => {
              const model = STRUCTURE_MODELS.find((m) => m.id === result.modelId);
              const isSelected = selectedResultModel === result.modelId;
              const isSuccess = result.status === 'success' && result.result;

              return (
                <div
                  key={result.modelId}
                  className={`structure-viewer-card ${isSelected ? 'selected' : ''}`}
                  onClick={() => isSuccess && handleSelectResult(result.modelId)}
                >
                  <div className="structure-viewer-card-header">
                    <div className="structure-viewer-card-title">
                      <span className="structure-viewer-card-name">{model?.name}</span>
                      <span className={`model-badge ${model?.badge.toLowerCase()}`}>{model?.badge}</span>
                    </div>
                    {isSelected && (
                      <span className="selected-badge">
                        <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                          <path d="M2 7l3 3 7-7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                        Selected
                      </span>
                    )}
                  </div>

                  {result.status === 'error' && (
                    <div className="result-error" style={{ margin: '1rem' }}>
                      <span className="result-error-icon">!</span>
                      <span className="result-error-message">{result.error}</span>
                    </div>
                  )}

                  {isSuccess && result.result && (
                    <>
                      <div className="structure-viewer-card-scores">
                        <div className="structure-viewer-score">
                          <span className="structure-viewer-score-label">Confidence</span>
                          <span className={`structure-viewer-score-value ${getScoreColor(result.result.confidenceScore)}`}>
                            {(result.result.confidenceScore * 100).toFixed(1)}%
                          </span>
                        </div>
                        <div className="structure-viewer-score">
                          <span className="structure-viewer-score-label">pLDDT</span>
                          <span className={`structure-viewer-score-value ${getScoreColor(result.result.plddt, 100)}`}>
                            {result.result.plddt.toFixed(1)}
                          </span>
                        </div>
                        <div className="structure-viewer-score">
                          <span className="structure-viewer-score-label">pTM</span>
                          <span className={`structure-viewer-score-value ${getScoreColor(result.result.ptm)}`}>
                            {result.result.ptm.toFixed(3)}
                          </span>
                        </div>
                        <div className="structure-viewer-score">
                          <span className="structure-viewer-score-label">Time</span>
                          <span className="structure-viewer-score-value" style={{ color: 'var(--color-violet)' }}>
                            {formatElapsedTime(result.elapsedTime)}
                          </span>
                        </div>
                      </div>

                      <StructureViewer
                        structure={result.result.structure}
                        format={result.result.format}
                        height={300}
                        colorScheme="confidence"
                      />

                      <div className="result-card-actions" style={{ padding: '0.75rem', borderTop: '1px solid var(--color-gray-200)' }}>
                        <button
                          className="btn btn-ghost btn-sm"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDownloadStructure(result.result!);
                          }}
                        >
                          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                            <path d="M7 1v8M3 6l4 4 4-4M2 12h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                          </svg>
                          Download {result.result.format.toUpperCase()}
                        </button>
                      </div>
                    </>
                  )}
                </div>
              );
            })}
          </div>

          {/* Re-run button */}
          <div className="results-actions">
            <button className="btn btn-ghost" onClick={handleRunAllPredictions}>
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M2 8a6 6 0 1 1 12 0A6 6 0 0 1 2 8z" stroke="currentColor" strokeWidth="1.5" />
                <path d="M8 4v4l2.5 1.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
              Re-run All Predictions
            </button>
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="step-actions">
        <button className="btn btn-ghost" onClick={onBack}>
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M12.5 15l-5-5 5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Back
        </button>
        <button
          className="btn btn-secondary btn-lg"
          disabled={!selectedResultModel}
          onClick={handleContinue}
        >
          Continue with {selectedResultModel ? STRUCTURE_MODELS.find((m) => m.id === selectedResultModel)?.name : 'Selected'} Result
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M7.5 15l5-5-5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>

    </div>
  );
}
