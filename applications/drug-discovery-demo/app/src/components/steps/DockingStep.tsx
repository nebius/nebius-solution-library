import { useState, useCallback, useMemo, useRef } from 'react';
import type { StructurePredictionResult } from '../../services/structurePrediction';
import type { GeneratedMolecule } from '../../services/moleculeGeneration';
import {
  type DockingResult,
  dockMultipleLigands,
  getBestDockingResults,
  getConfidenceLevel,
} from '../../services/docking';
import { StructureViewer } from '../StructureViewer';
import { MoleculeViewer2D } from '../MoleculeViewer2D';
import { DrugLikenessBadge } from '../DrugLikenessPanel';
import type { DrugTarget } from '../../data/drugs';
import { formatDuration, formatEta } from '../../hooks/useProgressTracker';


interface DockingStepProps {
  structureResult: StructurePredictionResult | null;
  generatedMolecules: GeneratedMolecule[];
  selectedDrug: DrugTarget | null;
  gatewayUrl: string;
  onDockingResults: (results: DockingResult[]) => void;
  onContinue: () => void;
  onBack: () => void;
}

export function DockingStep({
  structureResult,
  generatedMolecules,
  selectedDrug,
  gatewayUrl,
  onDockingResults,
  onContinue,
  onBack,
}: DockingStepProps) {
  // Auto-select top 10 molecules plus reference molecule
  const [selectedMolecules, setSelectedMolecules] = useState<Set<number>>(() => {
    const indices = new Set(generatedMolecules.slice(0, 10).map((_, i) => i));
    // Also select the reference molecule if it exists
    const refIndex = generatedMolecules.findIndex((m) => m.isReference);
    if (refIndex !== -1) {
      indices.add(refIndex);
    }
    return indices;
  });
  const [isProcessing, setIsProcessing] = useState(false);
  const [progress, setProgress] = useState({ completed: 0, total: 0, startTime: 0, completionTimes: [] as number[] });
  const [results, setResults] = useState<DockingResult[]>([]);
  const lastCompletionTimeRef = useRef<number>(0);
  const [selectedResults, setSelectedResults] = useState<Set<string>>(new Set());
  const [numPoses, setNumPoses] = useState(30); // 30 is optimal per 2024 research
  const [parallelism, setParallelism] = useState(3); // Number of parallel API calls
  const [viewingResult, setViewingResult] = useState<DockingResult | null>(null); // For 3D visualization
  const [dockingError, setDockingError] = useState<string | null>(null);

  // Get molecules to dock
  const moleculesToDock = useMemo(() => {
    return generatedMolecules.filter((_, i) => selectedMolecules.has(i));
  }, [generatedMolecules, selectedMolecules]);

  // Best results for display
  const bestResults = useMemo(() => {
    return getBestDockingResults(results, 20);
  }, [results]);

  const handleToggleMolecule = useCallback((index: number) => {
    setSelectedMolecules((prev) => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  }, []);

  const handleSelectTop = useCallback((n: number) => {
    setSelectedMolecules(new Set(generatedMolecules.slice(0, n).map((_, i) => i)));
  }, [generatedMolecules]);

  const handleSelectAll = useCallback(() => {
    setSelectedMolecules(new Set(generatedMolecules.map((_, i) => i)));
  }, [generatedMolecules]);

  const handleSelectNone = useCallback(() => {
    setSelectedMolecules(new Set());
  }, []);

  const handleRunDocking = useCallback(async () => {
    if (!structureResult || moleculesToDock.length === 0 || !gatewayUrl) return;

    const startTime = Date.now();
    setIsProcessing(true);
    setDockingError(null);
    setProgress({ completed: 0, total: moleculesToDock.length, startTime, completionTimes: [] });
    lastCompletionTimeRef.current = startTime;
    setResults([]);
    setSelectedResults(new Set());

    try {
      const smilesList = moleculesToDock.map((m) => m.smiles);

      const dockingResults = await dockMultipleLigands(
        gatewayUrl,
        structureResult.structure,
        structureResult.format,
        smilesList,
        numPoses,
        (completed, total, result) => {
          const now = Date.now();
          const timeSinceLast = now - lastCompletionTimeRef.current;
          lastCompletionTimeRef.current = now;

          setProgress((prev) => ({
            completed,
            total,
            startTime: prev.startTime,
            completionTimes: [...prev.completionTimes, timeSinceLast],
          }));
          if (result && result.poses.length > 0) {
            setResults((prev) => [...prev, result]);
          }
        },
        parallelism
      );

      // Auto-select top 5 results plus reference molecule if docked
      const topResults = getBestDockingResults(dockingResults, 5);
      const selectedSmiles = new Set(topResults.map((r) => r.ligandSmiles));

      // Also select the reference molecule result if it exists
      if (selectedDrug?.referenceSMILES) {
        const refResult = dockingResults.find(
          (r) => r.ligandSmiles.toLowerCase() === selectedDrug.referenceSMILES.toLowerCase()
        );
        if (refResult) {
          selectedSmiles.add(refResult.ligandSmiles);
        }
      }

      setSelectedResults(selectedSmiles);
      onDockingResults(dockingResults);
    } catch (error) {
      console.error('Docking failed:', error);
      setDockingError(error instanceof Error ? error.message : 'Docking failed. Please check the NIM gateway connection and try again.');
    }

    setIsProcessing(false);
  }, [structureResult, moleculesToDock, gatewayUrl, numPoses, parallelism, onDockingResults]);

  const handleToggleResult = useCallback((smiles: string) => {
    setSelectedResults((prev) => {
      const next = new Set(prev);
      if (next.has(smiles)) {
        next.delete(smiles);
      } else {
        next.add(smiles);
      }
      return next;
    });
  }, []);

  const handleContinue = useCallback(() => {
    onContinue();
  }, [onContinue]);

  const getScoreColor = (score: number) => {
    const level = getConfidenceLevel(score);
    return `score-${level}`;
  };

  if (!structureResult) {
    return (
      <div className="step-content">
        <div className="content-header">
          <div>
            <h1 className="content-title">Molecular Docking</h1>
            <p className="content-subtitle">Please predict a protein structure first.</p>
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

  if (generatedMolecules.length === 0) {
    return (
      <div className="step-content">
        <div className="content-header">
          <div>
            <h1 className="content-title">Molecular Docking</h1>
            <p className="content-subtitle">Please generate candidate molecules first.</p>
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
          <h1 className="content-title">Molecular Docking</h1>
          <p className="content-subtitle">
            Use DiffDock to predict binding poses and validate which molecules bind to the target protein.
          </p>
        </div>
      </div>

      {/* Target Structure Preview */}
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Target Protein Structure</h3>
          <span className="card-badge">{structureResult.modelUsed}</span>
        </div>
        <div className="docking-structure-preview">
          <StructureViewer
            structure={structureResult.structure}
            format={structureResult.format}
            height={250}
            showControls={false}
          />
        </div>
        <div className="structure-stats">
          <div className="stat-item">
            <span className="stat-label">Confidence</span>
            <span className={`stat-value ${getScoreColor(structureResult.confidenceScore)}`}>
              {(structureResult.confidenceScore * 100).toFixed(1)}%
            </span>
          </div>
          <div className="stat-item">
            <span className="stat-label">pLDDT</span>
            <span className={`stat-value ${getScoreColor(structureResult.plddt / 100)}`}>
              {structureResult.plddt.toFixed(1)}
            </span>
          </div>
          <div className="stat-item">
            <span className="stat-label">Format</span>
            <span className="stat-value">{structureResult.format.toUpperCase()}</span>
          </div>
        </div>
      </div>

      {/* Docking Error */}
      {dockingError && !isProcessing && (
        <div className="card" style={{ borderColor: 'var(--color-danger)', background: 'var(--color-danger-bg, rgba(239, 68, 68, 0.1))' }}>
          <div className="card-header">
            <h3 className="card-title" style={{ color: 'var(--color-danger)' }}>Docking Failed</h3>
          </div>
          <p style={{ padding: '0 var(--space-4) var(--space-4)', color: 'var(--color-text-secondary)' }}>
            {dockingError}
          </p>
        </div>
      )}

      {/* Molecule Selection */}
      {results.length === 0 && !isProcessing && (
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">Select Molecules to Dock</h3>
            <div className="molecules-selection-controls">
              <button className="btn btn-ghost btn-sm" onClick={() => handleSelectTop(5)}>
                Top 5
              </button>
              <button className="btn btn-ghost btn-sm" onClick={() => handleSelectTop(10)}>
                Top 10
              </button>
              <button className="btn btn-ghost btn-sm" onClick={handleSelectAll}>
                All
              </button>
              <button className="btn btn-ghost btn-sm" onClick={handleSelectNone}>
                None
              </button>
            </div>
          </div>

          <div className="molecules-selected-count">
            <span className="selected-count-number">{selectedMolecules.size}</span>
            <span className="selected-count-label">molecules selected for docking</span>
          </div>

          <div className="molecules-grid">
            {generatedMolecules.map((mol, index) => {
              const isSelected = selectedMolecules.has(index);
              return (
                <div
                  key={index}
                  className={`molecule-card ${isSelected ? 'selected' : ''} ${mol.isReference ? 'reference' : ''}`}
                  onClick={() => handleToggleMolecule(index)}
                >
                  <div className="molecule-card-header">
                    <span className="molecule-rank">#{index + 1}</span>
                    {mol.isReference && (
                      <span className="molecule-reference-badge">
                        <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                          <path d="M6 1l5 3v4l-5 3-5-3V4l5-3z" stroke="currentColor" strokeWidth="1.5" />
                        </svg>
                        {selectedDrug?.name || 'Reference'}
                      </span>
                    )}
                    <span className={`molecule-score ${getScoreColor(mol.score)}`}>
                      QED: {mol.score.toFixed(3)}
                    </span>
                    {isSelected && (
                      <span className="molecule-selected-icon">
                        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                          <path d="M2 8l4 4 8-8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      </span>
                    )}
                  </div>
                  {/* 2D Molecule Structure */}
                  <div className="molecule-card-structure">
                    <MoleculeViewer2D smiles={mol.smiles} width={140} height={100} />
                  </div>
                  {/* Drug-Likeness Badge */}
                  <DrugLikenessBadge smiles={mol.smiles} />
                  <p className="molecule-smiles-preview">
                    {mol.smiles.length > 40 ? `${mol.smiles.substring(0, 40)}...` : mol.smiles}
                  </p>
                </div>
              );
            })}
          </div>

          {/* Docking Parameters */}
          <div className="docking-parameters">
            <h4 className="docking-parameters-title">Docking Parameters</h4>
            <div className="parameter-grid">
              <div className="parameter-item">
                <label className="parameter-label">Poses per Ligand</label>
                <input
                  type="number"
                  className="parameter-input"
                  value={numPoses}
                  onChange={(e) => setNumPoses(Math.max(1, Math.min(40, parseInt(e.target.value) || 30)))}
                  min={1}
                  max={40}
                />
                <span className="parameter-hint">30 poses recommended (2024 research optimal)</span>
              </div>
            </div>
          </div>

          {/* Nebius Boost */}
          <div className="nebius-boost-section">
            <div className="nebius-boost-header">
              <div className="nebius-boost-logo">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                  <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
              <div className="nebius-boost-title">
                <h4>Nebius Boost</h4>
                <p>Leverage multiple DiffDock instances for faster processing</p>
              </div>
              <label className="nebius-boost-toggle">
                <input
                  type="checkbox"
                  checked={parallelism > 1}
                  onChange={(e) => setParallelism(e.target.checked ? 3 : 1)}
                />
                <span className="toggle-slider" />
              </label>
            </div>

            {parallelism > 1 && (
              <div className="nebius-boost-speeds">
                <span className="boost-speed-label">Speed Factor:</span>
                <div className="boost-speed-options">
                  {[2, 3, 5, 8, 10].map((speed) => (
                    <button
                      key={speed}
                      className={`boost-speed-btn ${parallelism === speed ? 'active' : ''}`}
                      onClick={() => setParallelism(speed)}
                    >
                      {speed}x
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Run Button */}
          <div className="docking-action">
            <button
              className="btn btn-primary btn-lg"
              onClick={handleRunDocking}
              disabled={selectedMolecules.size === 0 || !gatewayUrl}
            >
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <path d="M4 4l12 6-12 6V4z" fill="currentColor" />
              </svg>
              Dock {selectedMolecules.size} Molecule{selectedMolecules.size !== 1 ? 's' : ''} with DiffDock
            </button>
            {!gatewayUrl && (
              <p className="prediction-hint">Enter NIM Gateway URL to continue</p>
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
            <h3 className="processing-title">Running DiffDock</h3>
            <p className="processing-description">
              Docking molecules to target protein...
            </p>
            <div className="docking-progress">
              <div className="progress-bar">
                <div
                  className="progress-fill"
                  style={{ width: `${(progress.completed / progress.total) * 100}%` }}
                />
              </div>
              <span className="progress-text">
                {progress.completed} / {progress.total} molecules docked
              </span>
              {/* ETA display */}
              <div className="progress-eta">
                {(() => {
                  const elapsed = Date.now() - progress.startTime;
                  const avgTimePerItem = progress.completionTimes.length > 0
                    ? progress.completionTimes.reduce((a, b) => a + b, 0) / progress.completionTimes.length
                    : progress.completed > 0 ? elapsed / progress.completed : null;
                  const remaining = progress.total - progress.completed;
                  const eta = avgTimePerItem !== null ? avgTimePerItem * remaining : null;

                  return (
                    <>
                      <span className="progress-elapsed">Elapsed: {formatDuration(elapsed)}</span>
                      {progress.completed > 0 && (
                        <span className="progress-eta-time">{formatEta(eta)}</span>
                      )}
                    </>
                  );
                })()}
              </div>
            </div>
            {results.length > 0 && (
              <div className="docking-live-results">
                <p className="live-results-label">
                  {results.length} successful dock{results.length !== 1 ? 's' : ''} so far
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Results */}
      {results.length > 0 && !isProcessing && (
        <div className="docking-results">
          <div className="docking-results-header">
            <h3 className="docking-results-title">
              Docking Results
              <span className="docking-results-subtitle">
                {results.length} molecules docked successfully. Select candidates for rediscovery analysis.
              </span>
            </h3>
          </div>

          <div className="docking-results-summary">
            <div className="summary-stat">
              <span className="summary-stat-value">{results.length}</span>
              <span className="summary-stat-label">Docked</span>
            </div>
            <div className="summary-stat">
              <span className="summary-stat-value">
                {bestResults.length > 0 ? (bestResults[0].bestConfidence * 100).toFixed(1) : 0}%
              </span>
              <span className="summary-stat-label">Best Confidence</span>
            </div>
            <div className="summary-stat">
              <span className="summary-stat-value">{selectedResults.size}</span>
              <span className="summary-stat-label">Selected</span>
            </div>
          </div>

          <div className="docking-results-grid">
            {bestResults.map((result, index) => {
              const isSelected = selectedResults.has(result.ligandSmiles);
              const confidenceLevel = getConfidenceLevel(result.bestConfidence);
              const isReference = selectedDrug?.referenceSMILES?.toLowerCase() === result.ligandSmiles.toLowerCase();

              return (
                <div
                  key={result.ligandSmiles}
                  className={`docking-result-card ${isSelected ? 'selected' : ''} ${isReference ? 'reference' : ''}`}
                  onClick={() => handleToggleResult(result.ligandSmiles)}
                >
                  <div className="docking-result-header">
                    <span className="docking-result-rank">#{index + 1}</span>
                    {isReference && (
                      <span className="molecule-reference-badge">
                        <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                          <path d="M6 1l5 3v4l-5 3-5-3V4l5-3z" stroke="currentColor" strokeWidth="1.5" />
                        </svg>
                        {selectedDrug?.name || 'Reference'}
                      </span>
                    )}
                    <span className={`docking-result-confidence confidence-${confidenceLevel}`}>
                      {(result.bestConfidence * 100).toFixed(1)}%
                    </span>
                    {isSelected && (
                      <span className="selected-badge">
                        <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                          <path d="M2 7l3 3 7-7" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                        Selected
                      </span>
                    )}
                  </div>

                  {/* 2D Molecule Structure */}
                  <div className="docking-result-structure">
                    <MoleculeViewer2D smiles={result.ligandSmiles} width={180} height={120} />
                  </div>

                  {/* Drug-Likeness Badge */}
                  <DrugLikenessBadge smiles={result.ligandSmiles} />

                  <div className="docking-result-details">
                    <div className="docking-result-stat">
                      <span className="docking-stat-label">Poses</span>
                      <span className="docking-stat-value">{result.poses.length}</span>
                    </div>
                    <div className="docking-result-stat">
                      <span className="docking-stat-label">Time</span>
                      <span className="docking-stat-value">{(result.elapsedTime / 1000).toFixed(1)}s</span>
                    </div>
                  </div>

                  {result.poses.length > 0 && (
                    <>
                      <div className="docking-poses-preview">
                        <span className="poses-label">Top Pose Confidence:</span>
                        <div className="poses-list">
                          {result.poses.slice(0, 3).map((pose, i) => (
                            <span key={i} className={`pose-confidence ${getConfidenceLevel(pose.confidence)}`}>
                              {(pose.confidence * 100).toFixed(0)}%
                          </span>
                        ))}
                      </div>
                    </div>
                    <button
                      className="btn btn-outline btn-sm docking-view-3d-btn"
                      onClick={(e) => {
                        e.stopPropagation();
                        setViewingResult(result);
                      }}
                    >
                      <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                        <path d="M7 1l6 3.5v5L7 13l-6-3.5v-5L7 1z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
                        <path d="M7 5.5v4M1 4.5L7 8l6-3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                      </svg>
                      View 3D
                    </button>
                  </>
                  )}
                </div>
              );
            })}
          </div>

          {/* 3D Pose Viewer */}
          {viewingResult && structureResult && (
            <div className="card docking-pose-viewer-card">
              <div className="card-header">
                <h3 className="card-title">
                  Docked Pose Visualization
                  <span className="card-subtitle">
                    {viewingResult.poses.length} pose{viewingResult.poses.length !== 1 ? 's' : ''} for ligand
                  </span>
                </h3>
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={() => setViewingResult(null)}
                >
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                    <path d="M3 3l8 8M11 3l-8 8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                  </svg>
                  Close
                </button>
              </div>
              <div className="docking-pose-smiles">
                <code>{viewingResult.ligandSmiles}</code>
              </div>
              <StructureViewer
                structure={structureResult.structure}
                format={structureResult.format}
                height={400}
                showControls={true}
                ligands={viewingResult.poses.map((pose, i) => ({
                  sdf: pose.ligand_positions,
                  label: `Pose ${i + 1} (${(pose.confidence * 100).toFixed(0)}%)`,
                  color: i === 0 ? '#00ff00' : i === 1 ? '#ff6600' : '#00ccff',
                }))}
              />
              <div className="docking-pose-legend">
                {viewingResult.poses.slice(0, 3).map((pose, i) => (
                  <div key={i} className="pose-legend-item">
                    <span
                      className="pose-legend-color"
                      style={{ backgroundColor: i === 0 ? '#00ff00' : i === 1 ? '#ff6600' : '#00ccff' }}
                    />
                    <span className="pose-legend-label">
                      Pose {i + 1}: {(pose.confidence * 100).toFixed(1)}%
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Re-run button */}
          <div className="docking-actions">
            <button className="btn btn-ghost" onClick={() => {
              setResults([]);
              setSelectedResults(new Set());
            }}>
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M2 8a6 6 0 1 1 12 0A6 6 0 0 1 2 8z" stroke="currentColor" strokeWidth="1.5" />
                <path d="M8 4v4l2.5 1.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
              Re-configure Docking
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
          disabled={results.length === 0}
          onClick={handleContinue}
        >
          Continue to Rediscovery
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M7.5 15l5-5-5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>

    </div>
  );
}
