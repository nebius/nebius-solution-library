import { useState, useCallback, useMemo, useEffect } from 'react';
import type { DockingResult } from '../../services/docking';
import type { DrugTarget } from '../../data/drugs';
import {
  type RediscoveryResult,
  type SimilarityResult,
  analyzeRediscovery,
  formatSimilarity,
  getSimilarityLevel,
  getMolecularProperties,
} from '../../services/similarity';


interface RediscoveryStepProps {
  selectedDrug: DrugTarget | null;
  dockingResults: DockingResult[];
  onContinue: () => void;
  onBack: () => void;
}

export function RediscoveryStep({
  selectedDrug,
  dockingResults,
  onContinue,
  onBack,
}: RediscoveryStepProps) {
  const [rediscoveryResult, setRediscoveryResult] = useState<RediscoveryResult | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [selectedMolecule, setSelectedMolecule] = useState<SimilarityResult | null>(null);

  // Get unique SMILES from docking results (only successful docks)
  const dockedSmiles = useMemo(() => {
    return dockingResults
      .filter((r) => r.poses.length > 0)
      .map((r) => r.ligandSmiles);
  }, [dockingResults]);

  // Get docking info for a SMILES
  const getDockingInfo = useCallback(
    (smiles: string): DockingResult | undefined => {
      return dockingResults.find((r) => r.ligandSmiles === smiles);
    },
    [dockingResults]
  );

  // Run analysis when data is available
  useEffect(() => {
    if (!selectedDrug || !selectedDrug.referenceSMILES || dockedSmiles.length === 0) {
      return;
    }

    setIsAnalyzing(true);

    // Use setTimeout to allow UI to update before heavy computation
    const timer = setTimeout(() => {
      const result = analyzeRediscovery(
        selectedDrug.referenceSMILES,
        selectedDrug.name,
        dockedSmiles
      );
      setRediscoveryResult(result);
      setIsAnalyzing(false);

      // Auto-select best match
      if (result.bestMatch) {
        setSelectedMolecule(result.bestMatch);
      }
    }, 100);

    return () => clearTimeout(timer);
  }, [selectedDrug, dockedSmiles]);

  // Reference molecule properties
  const referenceProps = useMemo(() => {
    if (!selectedDrug?.referenceSMILES) return null;
    return getMolecularProperties(selectedDrug.referenceSMILES);
  }, [selectedDrug]);

  // Selected molecule properties
  const selectedProps = useMemo(() => {
    if (!selectedMolecule) return null;
    return getMolecularProperties(selectedMolecule.smiles);
  }, [selectedMolecule]);

  if (!selectedDrug) {
    return (
      <div className="step-content">
        <div className="content-header">
          <div>
            <h1 className="content-title">Drug Rediscovery</h1>
            <p className="content-subtitle">Please select a drug target first.</p>
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

  if (dockingResults.length === 0) {
    return (
      <div className="step-content">
        <div className="content-header">
          <div>
            <h1 className="content-title">Drug Rediscovery</h1>
            <p className="content-subtitle">Please complete molecular docking first.</p>
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

  // Check if we found the exact drug or a high similarity match
  const isHighSimilarity = (rediscoveryResult?.bestMatch?.similarity || 0) >= 0.7;

  return (
    <div className="step-content">
      <div className="content-header">
        <div>
          <h1 className="content-title">Drug Rediscovery Analysis</h1>
          <p className="content-subtitle">
            Comparing {dockedSmiles.length} docked molecules to {selectedDrug.name} using Tanimoto similarity.
          </p>
        </div>
      </div>

      {/* Analysis Status */}
      {isAnalyzing && (
        <div className="card processing-card">
          <div className="processing-content">
            <div className="processing-spinner">
              <span className="spinner spinner-lg" />
            </div>
            <h3 className="processing-title">Analyzing Molecular Similarity</h3>
            <p className="processing-description">
              Computing fingerprints and Tanimoto coefficients...
            </p>
          </div>
        </div>
      )}

      {/* Results Summary */}
      {rediscoveryResult && !isAnalyzing && (
        <>
          {/* Success/Failure Banner */}
          <div className={`rediscovery-banner ${rediscoveryResult.exactMatch || isHighSimilarity ? 'success' : 'partial'}`}>
            <div className="rediscovery-banner-icon">
              {rediscoveryResult.exactMatch ? (
                <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
                  <circle cx="24" cy="24" r="22" stroke="currentColor" strokeWidth="3" />
                  <path d="M14 24l7 7 13-13" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              ) : isHighSimilarity ? (
                <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
                  <circle cx="24" cy="24" r="22" stroke="currentColor" strokeWidth="3" />
                  <path d="M24 14v20M14 24h20" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
                </svg>
              ) : (
                <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
                  <circle cx="24" cy="24" r="22" stroke="currentColor" strokeWidth="3" />
                  <path d="M24 16v12M24 32v2" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
                </svg>
              )}
            </div>
            <div className="rediscovery-banner-content">
              <h2 className="rediscovery-banner-title">
                {rediscoveryResult.exactMatch
                  ? `${selectedDrug.name} Exactly Rediscovered!`
                  : isHighSimilarity
                  ? `${selectedDrug.name} Successfully Rediscovered!`
                  : `${selectedDrug.name} - Similar Compounds Found`}
              </h2>
              <p className="rediscovery-banner-text">
                {rediscoveryResult.exactMatch
                  ? `One of the generated molecules is identical to ${selectedDrug.name}.`
                  : rediscoveryResult.bestMatch
                  ? `Best match: ${formatSimilarity(rediscoveryResult.bestMatch.similarity)} Tanimoto similarity`
                  : 'No similar molecules found in the docked candidates.'}
              </p>
            </div>
          </div>

          {/* Statistics */}
          <div className="rediscovery-stats">
            <div className="rediscovery-stat">
              <span className="rediscovery-stat-value">{dockedSmiles.length}</span>
              <span className="rediscovery-stat-label">Molecules Analyzed</span>
            </div>
            <div className="rediscovery-stat">
              <span className={`rediscovery-stat-value ${getSimilarityLevel(rediscoveryResult.bestMatch?.similarity || 0)}`}>
                {formatSimilarity(rediscoveryResult.bestMatch?.similarity || 0)}
              </span>
              <span className="rediscovery-stat-label">Best Similarity</span>
            </div>
            <div className="rediscovery-stat">
              <span className="rediscovery-stat-value">{rediscoveryResult.exactMatch ? 'Yes' : 'No'}</span>
              <span className="rediscovery-stat-label">Exact Match</span>
            </div>
          </div>

          {/* Comparison View */}
          <div className="rediscovery-comparison">
            {/* Reference Molecule */}
            <div className="comparison-card reference">
              <div className="comparison-header">
                <h3 className="comparison-title">Reference: {selectedDrug.name}</h3>
                <span className="comparison-badge reference-badge">Target</span>
              </div>
              <div className="comparison-smiles">
                <code>{selectedDrug.referenceSMILES}</code>
              </div>
              {referenceProps && (
                <div className="comparison-props">
                  <div className="prop-item">
                    <span className="prop-label">Formula</span>
                    <span className="prop-value">{referenceProps.formula}</span>
                  </div>
                  <div className="prop-item">
                    <span className="prop-label">MW</span>
                    <span className="prop-value">{referenceProps.molecularWeight.toFixed(1)}</span>
                  </div>
                  <div className="prop-item">
                    <span className="prop-label">Atoms</span>
                    <span className="prop-value">{referenceProps.atomCount}</span>
                  </div>
                  <div className="prop-item">
                    <span className="prop-label">Rings</span>
                    <span className="prop-value">{referenceProps.ringCount}</span>
                  </div>
                </div>
              )}
            </div>

            {/* Best Match */}
            {selectedMolecule && (
              <div className={`comparison-card match ${getSimilarityLevel(selectedMolecule.similarity)}`}>
                <div className="comparison-header">
                  <h3 className="comparison-title">Rank #{selectedMolecule.rank} Match</h3>
                  <span className={`comparison-badge similarity-badge ${getSimilarityLevel(selectedMolecule.similarity)}`}>
                    {formatSimilarity(selectedMolecule.similarity)}
                  </span>
                </div>
                <div className="comparison-smiles">
                  <code>{selectedMolecule.smiles}</code>
                </div>
                {selectedProps && (
                  <div className="comparison-props">
                    <div className="prop-item">
                      <span className="prop-label">Formula</span>
                      <span className="prop-value">{selectedProps.formula}</span>
                    </div>
                    <div className="prop-item">
                      <span className="prop-label">MW</span>
                      <span className="prop-value">{selectedProps.molecularWeight.toFixed(1)}</span>
                    </div>
                    <div className="prop-item">
                      <span className="prop-label">Atoms</span>
                      <span className="prop-value">{selectedProps.atomCount}</span>
                    </div>
                    <div className="prop-item">
                      <span className="prop-label">Rings</span>
                      <span className="prop-value">{selectedProps.ringCount}</span>
                    </div>
                  </div>
                )}
                {/* Docking info */}
                {(() => {
                  const dockingInfo = getDockingInfo(selectedMolecule.smiles);
                  if (!dockingInfo) return null;
                  return (
                    <div className="comparison-docking">
                      <div className="prop-item">
                        <span className="prop-label">Dock Confidence</span>
                        <span className="prop-value">{(dockingInfo.bestConfidence * 100).toFixed(1)}%</span>
                      </div>
                      <div className="prop-item">
                        <span className="prop-label">Poses</span>
                        <span className="prop-value">{dockingInfo.poses.length}</span>
                      </div>
                    </div>
                  );
                })()}
              </div>
            )}
          </div>

          {/* All Results Table */}
          <div className="card">
            <div className="card-header">
              <h3 className="card-title">Similarity Rankings</h3>
              <span className="card-subtitle">Click a row to compare with reference</span>
            </div>
            <div className="similarity-table-container">
              <table className="similarity-table">
                <thead>
                  <tr>
                    <th>Rank</th>
                    <th>Similarity</th>
                    <th>SMILES</th>
                    <th>Dock Score</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {rediscoveryResult.similarities.slice(0, 20).map((sim) => {
                    const dockingInfo = getDockingInfo(sim.smiles);
                    const isSelected = selectedMolecule?.smiles === sim.smiles;
                    const level = getSimilarityLevel(sim.similarity);
                    return (
                      <tr
                        key={sim.smiles}
                        className={`similarity-row ${isSelected ? 'selected' : ''} ${level}`}
                        onClick={() => setSelectedMolecule(sim)}
                      >
                        <td className="rank-cell">#{sim.rank}</td>
                        <td className={`similarity-cell ${level}`}>
                          {formatSimilarity(sim.similarity)}
                        </td>
                        <td className="smiles-cell">
                          <code>{sim.smiles.length > 50 ? `${sim.smiles.substring(0, 50)}...` : sim.smiles}</code>
                        </td>
                        <td className="dock-cell">
                          {dockingInfo ? `${(dockingInfo.bestConfidence * 100).toFixed(1)}%` : '-'}
                        </td>
                        <td className="status-cell">
                          <span className={`status-badge ${level}`}>
                            {level === 'exact' ? 'Exact' : level === 'high' ? 'High' : level === 'medium' ? 'Medium' : 'Low'}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {rediscoveryResult.similarities.length > 20 && (
              <div className="table-footer">
                Showing top 20 of {rediscoveryResult.similarities.length} molecules
              </div>
            )}
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
          disabled={!rediscoveryResult}
          onClick={onContinue}
        >
          View Summary
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M7.5 15l5-5-5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>

    </div>
  );
}
