import { useState, useCallback, useEffect } from 'react';
import { buildNimUrl } from '../../services/nimApi';
import { StructureViewer } from '../StructureViewer';
import type { ProteinDesignResult } from './ProteinDesignStep';
import { formatDuration } from '../../hooks/useProgressTracker';

interface SequenceDesignStepProps {
  designedStructure: ProteinDesignResult | null;
  gatewayUrl: string;
  onSequenceResult: (result: SequenceDesignResult) => void;
  onContinue: () => void;
  onBack: () => void;
}

export interface DesignedSequence {
  sequence: string;
  score: number;
  recoveryRate?: number;
}

export interface SequenceDesignResult {
  sequences: DesignedSequence[];
  backboneStructure: string;
  temperature: number;
}

export function SequenceDesignStep({
  designedStructure,
  gatewayUrl,
  onSequenceResult,
  onContinue,
  onBack,
}: SequenceDesignStepProps) {
  // Design parameters
  const [numSequences, setNumSequences] = useState(4);
  const [temperature, setTemperature] = useState(0.1);
  const [fixedPositions, setFixedPositions] = useState('');

  // Processing state
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SequenceDesignResult | null>(null);
  const [selectedSequenceIndex, setSelectedSequenceIndex] = useState<number>(0);
  const [elapsedTime, setElapsedTime] = useState<number | null>(null);
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

  const handleRunDesign = useCallback(async () => {
    if (!gatewayUrl || !designedStructure) return;

    const now = Date.now();
    setStartTime(now);
    setLiveElapsedTime(0);
    setIsProcessing(true);
    setError(null);
    setResult(null);

    try {
      const proteinmpnnUrl = buildNimUrl(gatewayUrl, 8009, '/biology/ipd/proteinmpnn/predict');

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const requestBody: any = {
        pdb: designedStructure.structure,
        num_seq_per_target: numSequences,
        sampling_temp: temperature,
      };

      if (fixedPositions.trim()) {
        requestBody.fixed_positions = fixedPositions
          .split(',')
          .map((p) => parseInt(p.trim()))
          .filter((n) => !isNaN(n));
      }

      const response = await fetch(proteinmpnnUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody),
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`ProteinMPNN failed: ${response.status} - ${errorText}`);
      }

      const data = await response.json();
      const elapsed = Date.now() - now;
      setElapsedTime(elapsed);

      // Parse ProteinMPNN response
      const sequences: DesignedSequence[] = [];
      const rawSequences = data.sequences || data.designed_sequences || [];
      const rawScores = data.scores || data.sequence_scores || [];
      const rawRecovery = data.recovery_rates || [];

      for (let i = 0; i < rawSequences.length; i++) {
        sequences.push({
          sequence: rawSequences[i],
          score: rawScores[i] ?? 0,
          recoveryRate: rawRecovery[i],
        });
      }

      // Sort by score (lower is better for ProteinMPNN)
      sequences.sort((a, b) => a.score - b.score);

      const designResult: SequenceDesignResult = {
        sequences,
        backboneStructure: designedStructure.structure,
        temperature,
      };

      setResult(designResult);
      setSelectedSequenceIndex(0);
      onSequenceResult(designResult);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'ProteinMPNN failed';
      setError(message);
    } finally {
      setIsProcessing(false);
    }
  }, [gatewayUrl, designedStructure, numSequences, temperature, fixedPositions, onSequenceResult]);

  const handleContinue = useCallback(() => {
    if (result) {
      onContinue();
    }
  }, [result, onContinue]);


  if (!designedStructure) {
    return (
      <div className="step-content">
        <div className="content-header">
          <div>
            <h1 className="content-title">Sequence Design (ProteinMPNN)</h1>
            <p className="content-subtitle">Please design a protein structure first.</p>
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
          <h1 className="content-title">Sequence Design (ProteinMPNN)</h1>
          <p className="content-subtitle">
            Design amino acid sequences that will fold into your designed backbone structure.
          </p>
        </div>
      </div>

      {/* Backbone Structure Preview */}
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Backbone Structure</h3>
          <span className="card-badge">{designedStructure.mode} design</span>
        </div>
        <StructureViewer
          structure={designedStructure.structure}
          format="pdb"
          height={250}
          colorScheme="spectrum"
        />
      </div>

      {/* Design Parameters */}
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Design Parameters</h3>
        </div>
        <div className="design-params-grid">
          <div className="design-param">
            <label className="design-param-label">Number of Sequences</label>
            <input
              type="number"
              className="design-param-input"
              value={numSequences}
              onChange={(e) => setNumSequences(Math.max(1, Math.min(16, parseInt(e.target.value) || 4)))}
              min={1}
              max={16}
              disabled={isProcessing}
            />
            <span className="design-param-hint">1-16 sequences per design</span>
          </div>

          <div className="design-param">
            <label className="design-param-label">Sampling Temperature</label>
            <input
              type="number"
              className="design-param-input"
              value={temperature}
              onChange={(e) => setTemperature(Math.max(0.01, Math.min(1.0, parseFloat(e.target.value) || 0.1)))}
              min={0.01}
              max={1.0}
              step={0.01}
              disabled={isProcessing}
            />
            <span className="design-param-hint">Lower = more conservative (0.01-1.0)</span>
          </div>

          <div className="design-param design-param-full">
            <label className="design-param-label">Fixed Positions (optional)</label>
            <input
              type="text"
              className="design-param-input"
              value={fixedPositions}
              onChange={(e) => setFixedPositions(e.target.value)}
              placeholder="e.g., 10, 15, 20, 25"
              disabled={isProcessing}
            />
            <span className="design-param-hint">Comma-separated residue positions to keep unchanged</span>
          </div>
        </div>
      </div>

      {/* Run Button */}
      {!result && !isProcessing && (
        <div className="card generate-card">
          <div className="generate-content">
            <div className="generate-icon">
              <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
                <rect width="48" height="48" rx="12" fill="var(--color-lime)" />
                <text x="24" y="32" fontSize="24" textAnchor="middle" fill="var(--color-deep-blue)">A</text>
              </svg>
            </div>
            <h3 className="generate-title">Ready to Design Sequences</h3>
            <p className="generate-description">
              ProteinMPNN will design {numSequences} amino acid sequence{numSequences > 1 ? 's' : ''} that should fold into the designed backbone.
            </p>
            <button
              className="btn btn-primary btn-lg"
              onClick={handleRunDesign}
              disabled={!gatewayUrl}
            >
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <path d="M4 4l12 6-12 6V4z" fill="currentColor" />
              </svg>
              Run ProteinMPNN
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
            <h3 className="processing-title">Designing Sequences</h3>
            <p className="processing-description">
              ProteinMPNN is generating {numSequences} sequence{numSequences > 1 ? 's' : ''} for your backbone...
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
          <button className="btn btn-outline btn-sm" onClick={handleRunDesign}>
            Try Again
          </button>
        </div>
      )}

      {/* Results */}
      {result && result.sequences.length > 0 && (
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">Designed Sequences</h3>
            <div className="card-header-actions">
              <span className="card-badge success">{result.sequences.length} designs</span>
              {elapsedTime && (
                <span className="card-badge">{formatDuration(elapsedTime)}</span>
              )}
            </div>
          </div>

          <div className="designed-sequences-list">
            {result.sequences.map((seq, index) => (
              <div
                key={index}
                className={`designed-sequence-item ${selectedSequenceIndex === index ? 'selected' : ''}`}
                onClick={() => setSelectedSequenceIndex(index)}
              >
                <div className="designed-sequence-header">
                  <span className="designed-sequence-rank">#{index + 1}</span>
                  <span className="designed-sequence-score">
                    Score: {seq.score.toFixed(3)}
                  </span>
                  {seq.recoveryRate !== undefined && (
                    <span className="designed-sequence-recovery">
                      Recovery: {(seq.recoveryRate * 100).toFixed(1)}%
                    </span>
                  )}
                  {selectedSequenceIndex === index && (
                    <span className="selected-indicator">
                      <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                        <path d="M2 7l3 3 7-7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                    </span>
                  )}
                </div>
                <div className="designed-sequence-content">
                  <code className="designed-sequence-text">
                    {seq.sequence.length > 100
                      ? `${seq.sequence.slice(0, 50)}...${seq.sequence.slice(-50)}`
                      : seq.sequence}
                  </code>
                  <span className="designed-sequence-length">{seq.sequence.length} aa</span>
                </div>
              </div>
            ))}
          </div>

          {/* Selected Sequence Details */}
          {result.sequences[selectedSequenceIndex] && (
            <div className="selected-sequence-details">
              <div className="selected-sequence-header">
                <h4>Selected Sequence (#{selectedSequenceIndex + 1})</h4>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => navigator.clipboard.writeText(result.sequences[selectedSequenceIndex].sequence)}
                >
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                    <rect x="4" y="4" width="8" height="8" rx="1" stroke="currentColor" strokeWidth="1.5" />
                    <path d="M2 10V3a1 1 0 0 1 1-1h7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                  </svg>
                  Copy
                </button>
              </div>
              <div className="sequence-display">
                <div className="sequence-content">
                  <code className="sequence-text">
                    {result.sequences[selectedSequenceIndex].sequence.match(/.{1,60}/g)?.map((chunk, i) => (
                      <div key={i} className="sequence-line">
                        <span className="sequence-position">{i * 60 + 1}</span>
                        <span className="sequence-chunk">{chunk}</span>
                      </div>
                    ))}
                  </code>
                </div>
              </div>
            </div>
          )}

          <div className="result-card-actions" style={{ padding: '0.75rem', borderTop: '1px solid var(--color-gray-200)' }}>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => {
                const seq = result.sequences[selectedSequenceIndex];
                const fasta = `>designed_sequence_${selectedSequenceIndex + 1} score=${seq.score.toFixed(3)}\n${seq.sequence}`;
                const blob = new Blob([fasta], { type: 'text/plain' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `designed_sequence_${selectedSequenceIndex + 1}.fasta`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
              }}
            >
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M7 1v8M3 6l4 4 4-4M2 12h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              Download FASTA
            </button>
            <button className="btn btn-ghost btn-sm" onClick={handleRunDesign}>
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M1 7a6 6 0 1 1 12 0A6 6 0 0 1 1 7z" stroke="currentColor" strokeWidth="1.5" />
                <path d="M7 3v4l2 1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
              Regenerate
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
          disabled={!result || result.sequences.length === 0}
          onClick={handleContinue}
        >
          Continue to Validation
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M7.5 15l5-5-5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>
    </div>
  );
}
