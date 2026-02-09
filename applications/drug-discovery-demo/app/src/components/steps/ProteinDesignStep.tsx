import { useState, useCallback, useEffect } from 'react';
import { buildNimUrl } from '../../services/nimApi';
import { StructureViewer } from '../StructureViewer';
import type { DrugTarget } from '../../data/drugs';
import { formatDuration } from '../../hooks/useProgressTracker';

interface ProteinDesignStepProps {
  selectedDrug: DrugTarget | null;
  gatewayUrl: string;
  targetStructure?: string; // For binder design - the target protein structure
  targetStructureFormat?: 'pdb' | 'cif';
  onDesignResult: (result: ProteinDesignResult) => void;
  onContinue: () => void;
  onBack: () => void;
}

export interface ProteinDesignResult {
  structure: string; // PDB format backbone
  mode: 'unconditional' | 'binder' | 'scaffold';
  length: number;
  numDesigns: number;
}

type DesignMode = 'unconditional' | 'binder' | 'scaffold';

export function ProteinDesignStep({
  selectedDrug,
  gatewayUrl,
  targetStructure,
  targetStructureFormat,
  onDesignResult,
  onContinue,
  onBack,
}: ProteinDesignStepProps) {
  // Design parameters
  const [designMode, setDesignMode] = useState<DesignMode>(
    selectedDrug?.workflowType === 'protein-binder' ? 'binder' : 'unconditional'
  );
  const [proteinLength, setProteinLength] = useState(100);
  const [numDesigns, setNumDesigns] = useState(1);
  const [hotspotResidues, setHotspotResidues] = useState('');

  // Processing state
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ProteinDesignResult | null>(null);
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
    if (!gatewayUrl) return;

    const now = Date.now();
    setStartTime(now);
    setLiveElapsedTime(0);
    setIsProcessing(true);
    setError(null);
    setResult(null);

    try {
      const rfdiffusionUrl = buildNimUrl(gatewayUrl, 8010, '/biology/ipd/rfdiffusion/generate');

      // Build request based on design mode
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const requestBody: any = {
        contigs: [`${proteinLength}`],
        num_designs: numDesigns,
      };

      if (designMode === 'binder' && targetStructure) {
        requestBody.pdb = targetStructure;
        // For binder mode: design binder chain that binds to target
        requestBody.contigs = [`A1-${proteinLength}`, 'B1-100']; // Binder chain A, target chain B

        if (hotspotResidues.trim()) {
          requestBody.hotspot_res = hotspotResidues
            .split(',')
            .map((r) => `B${r.trim()}`);
        }
      }

      const response = await fetch(rfdiffusionUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestBody),
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`RFDiffusion failed: ${response.status} - ${errorText}`);
      }

      const data = await response.json();
      const elapsed = Date.now() - now;
      setElapsedTime(elapsed);

      const designResult: ProteinDesignResult = {
        structure: data.structure || data.pdb || data.output,
        mode: designMode,
        length: proteinLength,
        numDesigns: numDesigns,
      };

      setResult(designResult);
      onDesignResult(designResult);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'RFDiffusion failed';
      setError(message);
    } finally {
      setIsProcessing(false);
    }
  }, [gatewayUrl, designMode, proteinLength, numDesigns, hotspotResidues, targetStructure, onDesignResult]);

  const handleContinue = useCallback(() => {
    if (result) {
      onContinue();
    }
  }, [result, onContinue]);


  return (
    <div className="step-content">
      <div className="content-header">
        <div>
          <h1 className="content-title">Protein Design (RFDiffusion)</h1>
          <p className="content-subtitle">
            {designMode === 'binder'
              ? 'Design a protein that binds to your target using RFDiffusion.'
              : 'Generate a novel protein backbone structure using RFDiffusion.'}
          </p>
        </div>
      </div>

      {/* Design Mode Selection */}
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Design Mode</h3>
        </div>
        <div className="design-mode-grid">
          <label className={`design-mode-option ${designMode === 'unconditional' ? 'selected' : ''}`}>
            <input
              type="radio"
              name="designMode"
              value="unconditional"
              checked={designMode === 'unconditional'}
              onChange={() => setDesignMode('unconditional')}
              disabled={isProcessing}
            />
            <div className="design-mode-content">
              <span className="design-mode-icon">
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                  <rect x="3" y="3" width="6" height="6" rx="1" stroke="currentColor" strokeWidth="1.5" />
                  <rect x="11" y="3" width="6" height="6" rx="1" stroke="currentColor" strokeWidth="1.5" />
                  <rect x="3" y="11" width="6" height="6" rx="1" stroke="currentColor" strokeWidth="1.5" />
                  <rect x="11" y="11" width="6" height="6" rx="1" stroke="currentColor" strokeWidth="1.5" />
                </svg>
              </span>
              <span className="design-mode-name">Unconditional</span>
              <span className="design-mode-description">Generate a completely novel protein fold</span>
            </div>
          </label>

          <label className={`design-mode-option ${designMode === 'binder' ? 'selected' : ''} ${!targetStructure ? 'disabled' : ''}`}>
            <input
              type="radio"
              name="designMode"
              value="binder"
              checked={designMode === 'binder'}
              onChange={() => setDesignMode('binder')}
              disabled={isProcessing || !targetStructure}
            />
            <div className="design-mode-content">
              <span className="design-mode-icon">
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                  <path d="M8 12l-2 2a2.828 2.828 0 01-4-4l2-2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                  <path d="M12 8l2-2a2.828 2.828 0 014 4l-2 2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                  <path d="M8 12l4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
              </span>
              <span className="design-mode-name">Binder Design</span>
              <span className="design-mode-description">
                {targetStructure ? 'Design a protein that binds to target' : 'Requires target structure'}
              </span>
            </div>
          </label>

          <label className={`design-mode-option ${designMode === 'scaffold' ? 'selected' : ''}`}>
            <input
              type="radio"
              name="designMode"
              value="scaffold"
              checked={designMode === 'scaffold'}
              onChange={() => setDesignMode('scaffold')}
              disabled={isProcessing}
            />
            <div className="design-mode-content">
              <span className="design-mode-icon">
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                  <path d="M3 17h14M5 17V9l5-5 5 5v8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  <path d="M8 17v-4h4v4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </span>
              <span className="design-mode-name">Scaffold</span>
              <span className="design-mode-description">Design with specific topology constraints</span>
            </div>
          </label>
        </div>
      </div>

      {/* Target Structure Preview (for binder mode) */}
      {designMode === 'binder' && targetStructure && (
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">Target Structure</h3>
            <span className="card-badge">Binding Target</span>
          </div>
          <StructureViewer
            structure={targetStructure}
            format={targetStructureFormat || 'pdb'}
            height={250}
            colorScheme="confidence"
          />
        </div>
      )}

      {/* Design Parameters */}
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Design Parameters</h3>
        </div>
        <div className="design-params-grid">
          <div className="design-param">
            <label className="design-param-label">Protein Length (residues)</label>
            <input
              type="number"
              className="design-param-input"
              value={proteinLength}
              onChange={(e) => setProteinLength(Math.max(50, Math.min(500, parseInt(e.target.value) || 100)))}
              min={50}
              max={500}
              disabled={isProcessing}
            />
            <span className="design-param-hint">50-500 residues</span>
          </div>

          <div className="design-param">
            <label className="design-param-label">Number of Designs</label>
            <input
              type="number"
              className="design-param-input"
              value={numDesigns}
              onChange={(e) => setNumDesigns(Math.max(1, Math.min(10, parseInt(e.target.value) || 1)))}
              min={1}
              max={10}
              disabled={isProcessing}
            />
            <span className="design-param-hint">1-10 designs per run</span>
          </div>

          {designMode === 'binder' && (
            <div className="design-param design-param-full">
              <label className="design-param-label">Hotspot Residues (optional)</label>
              <input
                type="text"
                className="design-param-input"
                value={hotspotResidues}
                onChange={(e) => setHotspotResidues(e.target.value)}
                placeholder="e.g., 45, 48, 52, 55"
                disabled={isProcessing}
              />
              <span className="design-param-hint">Comma-separated target residue numbers to focus binding</span>
            </div>
          )}
        </div>
      </div>

      {/* Run Button */}
      {!result && !isProcessing && (
        <div className="card generate-card">
          <div className="generate-content">
            <div className="generate-icon">
              <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
                <rect width="48" height="48" rx="12" fill="var(--color-violet)" />
                <path d="M24 14v20M14 24h20" stroke="white" strokeWidth="3" strokeLinecap="round" />
              </svg>
            </div>
            <h3 className="generate-title">Ready to Design</h3>
            <p className="generate-description">
              RFDiffusion will generate {numDesigns === 1 ? 'a novel' : `${numDesigns} novel`} protein backbone
              {numDesigns === 1 ? '' : 's'} of ~{proteinLength} residues
              {designMode === 'binder' ? ' designed to bind your target' : ''}.
            </p>
            <button
              className="btn btn-primary btn-lg"
              onClick={handleRunDesign}
              disabled={!gatewayUrl}
            >
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <path d="M4 4l12 6-12 6V4z" fill="currentColor" />
              </svg>
              Run RFDiffusion
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
            <h3 className="processing-title">Designing Protein Structure</h3>
            <p className="processing-description">
              RFDiffusion is generating {numDesigns === 1 ? 'a novel backbone' : `${numDesigns} novel backbones`}...
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

      {/* Result */}
      {result && (
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">Designed Structure</h3>
            <div className="card-header-actions">
              <span className="card-badge success">Complete</span>
              {elapsedTime && (
                <span className="card-badge">{formatDuration(elapsedTime)}</span>
              )}
            </div>
          </div>

          <div className="design-result-info">
            <div className="design-result-stat">
              <span className="design-result-stat-label">Mode</span>
              <span className="design-result-stat-value">{result.mode}</span>
            </div>
            <div className="design-result-stat">
              <span className="design-result-stat-label">Target Length</span>
              <span className="design-result-stat-value">{result.length} residues</span>
            </div>
          </div>

          <StructureViewer
            structure={result.structure}
            format="pdb"
            height={400}
            colorScheme="spectrum"
          />

          <div className="result-card-actions" style={{ padding: '0.75rem', borderTop: '1px solid var(--color-gray-200)' }}>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => {
                const blob = new Blob([result.structure], { type: 'text/plain' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `designed_protein_${result.mode}.pdb`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
              }}
            >
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M7 1v8M3 6l4 4 4-4M2 12h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              Download PDB
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
          disabled={!result}
          onClick={handleContinue}
        >
          Continue to Sequence Design
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M7.5 15l5-5-5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>
    </div>
  );
}
