import { useState, useCallback, useEffect } from 'react';
import { predictStructure, type StructurePredictionResult } from '../../services/structurePrediction';
import { StructureViewer } from '../StructureViewer';
import type { SequenceDesignResult } from './SequenceDesignStep';
import type { ProteinDesignResult } from './ProteinDesignStep';
import { formatDuration } from '../../hooks/useProgressTracker';

interface ValidationStepProps {
  designedStructure: ProteinDesignResult | null;
  sequenceResult: SequenceDesignResult | null;
  selectedSequenceIndex: number;
  gatewayUrl: string;
  onValidationResult: (result: ValidationResult) => void;
  onContinue: () => void;
  onBack: () => void;
}

export interface ValidationResult {
  originalBackbone: string;
  designedSequence: string;
  predictedStructure: StructurePredictionResult;
  plddt: number;
  ptm: number;
}

export function ValidationStep({
  designedStructure,
  sequenceResult,
  selectedSequenceIndex,
  gatewayUrl,
  onValidationResult,
  onContinue,
  onBack,
}: ValidationStepProps) {
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ValidationResult | null>(null);
  const [elapsedTime, setElapsedTime] = useState<number | null>(null);
  const [selectedModel, setSelectedModel] = useState<'openfold3' | 'boltz2'>('openfold3');
  const [liveElapsedTime, setLiveElapsedTime] = useState<number>(0);
  const [startTime, setStartTime] = useState<number>(0);

  // Live elapsed time tracking
  useEffect(() => {
    if (!isProcessing || startTime === 0) return;

    const interval = setInterval(() => {
      setLiveElapsedTime(Date.now() - startTime);
    }, 1000);

    return () => clearInterval(interval);
  }, [isProcessing, startTime]);

  const selectedSequence = sequenceResult?.sequences[selectedSequenceIndex];

  const handleValidate = useCallback(async () => {
    if (!gatewayUrl || !selectedSequence || !designedStructure) return;

    const now = Date.now();
    setStartTime(now);
    setLiveElapsedTime(0);
    setIsProcessing(true);
    setError(null);
    setResult(null);

    try {
      // Predict structure of the designed sequence
      const prediction = await predictStructure(
        gatewayUrl,
        selectedSequence.sequence,
        selectedModel
      );

      const elapsed = Date.now() - now;
      setElapsedTime(elapsed);

      const validationResult: ValidationResult = {
        originalBackbone: designedStructure.structure,
        designedSequence: selectedSequence.sequence,
        predictedStructure: prediction,
        plddt: prediction.plddt,
        ptm: prediction.ptm,
      };

      setResult(validationResult);
      onValidationResult(validationResult);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Structure prediction failed';
      setError(message);
    } finally {
      setIsProcessing(false);
    }
  }, [gatewayUrl, selectedSequence, designedStructure, selectedModel, onValidationResult]);


  const getScoreColor = (score: number, max: number = 1) => {
    const normalized = score / max;
    if (normalized >= 0.7) return 'score-high';
    if (normalized >= 0.4) return 'score-medium';
    return 'score-low';
  };

  const getQualityAssessment = (plddt: number, ptm: number) => {
    if (plddt >= 80 && ptm >= 0.7) {
      return {
        status: 'excellent',
        message: 'High confidence - the designed sequence is predicted to fold well into the intended structure.',
        color: 'var(--color-success)',
      };
    } else if (plddt >= 60 && ptm >= 0.5) {
      return {
        status: 'good',
        message: 'Moderate confidence - the design shows promise but may need optimization.',
        color: 'var(--color-warning)',
      };
    } else {
      return {
        status: 'needs-work',
        message: 'Low confidence - consider redesigning with different parameters or selecting a different sequence.',
        color: 'var(--color-error)',
      };
    }
  };

  if (!designedStructure || !sequenceResult || !selectedSequence) {
    return (
      <div className="step-content">
        <div className="content-header">
          <div>
            <h1 className="content-title">Structure Validation</h1>
            <p className="content-subtitle">Please complete protein and sequence design first.</p>
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
          <h1 className="content-title">Structure Validation</h1>
          <p className="content-subtitle">
            Predict the structure of your designed sequence to validate it folds as intended.
          </p>
        </div>
      </div>

      {/* Design Summary */}
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Design to Validate</h3>
          <span className="card-badge">Sequence #{selectedSequenceIndex + 1}</span>
        </div>
        <div className="validation-summary">
          <div className="validation-summary-item">
            <span className="validation-summary-label">Design Mode</span>
            <span className="validation-summary-value">{designedStructure.mode}</span>
          </div>
          <div className="validation-summary-item">
            <span className="validation-summary-label">Sequence Length</span>
            <span className="validation-summary-value">{selectedSequence.sequence.length} aa</span>
          </div>
          <div className="validation-summary-item">
            <span className="validation-summary-label">ProteinMPNN Score</span>
            <span className="validation-summary-value">{selectedSequence.score.toFixed(3)}</span>
          </div>
        </div>
        <div className="sequence-preview">
          <code className="sequence-preview-text">
            {selectedSequence.sequence.slice(0, 60)}
            {selectedSequence.sequence.length > 60 && '...'}
          </code>
        </div>
      </div>

      {/* Model Selection */}
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Validation Model</h3>
        </div>
        <div className="model-selection-row">
          <label className={`model-radio-option ${selectedModel === 'openfold3' ? 'selected' : ''}`}>
            <input
              type="radio"
              name="validationModel"
              value="openfold3"
              checked={selectedModel === 'openfold3'}
              onChange={() => setSelectedModel('openfold3')}
              disabled={isProcessing}
            />
            <div className="model-radio-content">
              <span className="model-radio-name">OpenFold3</span>
              <span className="model-radio-badge recommended">Recommended</span>
              <span className="model-radio-description">Best accuracy for de novo designs</span>
            </div>
          </label>

          <label className={`model-radio-option ${selectedModel === 'boltz2' ? 'selected' : ''}`}>
            <input
              type="radio"
              name="validationModel"
              value="boltz2"
              checked={selectedModel === 'boltz2'}
              onChange={() => setSelectedModel('boltz2')}
              disabled={isProcessing}
            />
            <div className="model-radio-content">
              <span className="model-radio-name">Boltz2</span>
              <span className="model-radio-badge fast">Fast</span>
              <span className="model-radio-description">Faster validation, good accuracy</span>
            </div>
          </label>
        </div>
      </div>

      {/* Run Button */}
      {!result && !isProcessing && (
        <div className="card generate-card">
          <div className="generate-content">
            <div className="generate-icon">
              <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
                <rect width="48" height="48" rx="12" fill="var(--color-success)" />
                <path d="M16 24l6 6 12-12" stroke="white" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>
            <h3 className="generate-title">Ready to Validate</h3>
            <p className="generate-description">
              {selectedModel === 'openfold3' ? 'OpenFold3' : 'Boltz2'} will predict the 3D structure of your designed sequence.
              High pLDDT and pTM scores indicate the sequence is likely to fold into the intended structure.
            </p>
            <button
              className="btn btn-primary btn-lg"
              onClick={handleValidate}
              disabled={!gatewayUrl}
            >
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <path d="M4 4l12 6-12 6V4z" fill="currentColor" />
              </svg>
              Validate Structure
            </button>
            {!gatewayUrl && (
              <p className="generate-hint">Enter the NIM Gateway URL in the sidebar to continue.</p>
            )}
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
            <h3 className="processing-title">Validating Design</h3>
            <p className="processing-description">
              Predicting structure of the designed sequence ({selectedSequence.sequence.length} residues)...
            </p>
            <div className="progress-eta" style={{ marginTop: 'var(--spacing-md)' }}>
              <span className="progress-elapsed">Elapsed: {formatDuration(liveElapsedTime)}</span>
            </div>
          </div>
        </div>
      )}

      {/* Error State */}
      {error && (
        <div className="card error-card">
          <div className="card-header">
            <h3 className="card-title">Error</h3>
            <span className="card-badge error">Failed</span>
          </div>
          <p className="error-message">{error}</p>
          <button className="btn btn-outline btn-sm" onClick={handleValidate}>
            Try Again
          </button>
        </div>
      )}

      {/* Results */}
      {result && (
        <>
          {/* Quality Assessment */}
          <div className="card" style={{ borderLeft: `4px solid ${getQualityAssessment(result.plddt, result.ptm).color}` }}>
            <div className="card-header">
              <h3 className="card-title">Validation Result</h3>
              <span className={`card-badge ${getQualityAssessment(result.plddt, result.ptm).status}`}>
                {getQualityAssessment(result.plddt, result.ptm).status.replace('-', ' ')}
              </span>
            </div>
            <p className="validation-assessment">
              {getQualityAssessment(result.plddt, result.ptm).message}
            </p>
            <div className="validation-scores">
              <div className="validation-score">
                <span className="validation-score-label">pLDDT</span>
                <span className={`validation-score-value ${getScoreColor(result.plddt, 100)}`}>
                  {result.plddt.toFixed(1)}
                </span>
                <span className="validation-score-max">/ 100</span>
              </div>
              <div className="validation-score">
                <span className="validation-score-label">pTM</span>
                <span className={`validation-score-value ${getScoreColor(result.ptm)}`}>
                  {result.ptm.toFixed(3)}
                </span>
                <span className="validation-score-max">/ 1.0</span>
              </div>
              <div className="validation-score">
                <span className="validation-score-label">Confidence</span>
                <span className={`validation-score-value ${getScoreColor(result.predictedStructure.confidenceScore)}`}>
                  {(result.predictedStructure.confidenceScore * 100).toFixed(1)}%
                </span>
              </div>
              {elapsedTime && (
                <div className="validation-score">
                  <span className="validation-score-label">Time</span>
                  <span className="validation-score-value" style={{ color: 'var(--color-violet)' }}>
                    {formatDuration(elapsedTime)}
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Structure Comparison */}
          <div className="card">
            <div className="card-header">
              <h3 className="card-title">Predicted Structure</h3>
              <span className="card-badge">{result.predictedStructure.modelUsed}</span>
            </div>
            <StructureViewer
              structure={result.predictedStructure.structure}
              format={result.predictedStructure.format}
              height={400}
              colorScheme="confidence"
            />
            <div className="result-card-actions" style={{ padding: '0.75rem', borderTop: '1px solid var(--color-gray-200)' }}>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => {
                  const blob = new Blob([result.predictedStructure.structure], { type: 'text/plain' });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement('a');
                  a.href = url;
                  const ext = result.predictedStructure.format === 'pdb' ? 'pdb' : 'cif';
                  a.download = `validated_design.${ext}`;
                  document.body.appendChild(a);
                  a.click();
                  document.body.removeChild(a);
                  URL.revokeObjectURL(url);
                }}
              >
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <path d="M7 1v8M3 6l4 4 4-4M2 12h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                Download {result.predictedStructure.format.toUpperCase()}
              </button>
              <button className="btn btn-ghost btn-sm" onClick={handleValidate}>
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <path d="M1 7a6 6 0 1 1 12 0A6 6 0 0 1 1 7z" stroke="currentColor" strokeWidth="1.5" />
                  <path d="M7 3v4l2 1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
                Re-validate
              </button>
            </div>
          </div>
        </>
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
          disabled={!result}
          onClick={onContinue}
        >
          Continue to Summary
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M7.5 15l5-5-5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>
    </div>
  );
}
