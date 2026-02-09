import { useMemo } from 'react';
import {
  calculateDrugLikeness,
  getDrugLikenessLabel,
} from '../services/drugLikeness';

interface DrugLikenessPanelProps {
  smiles: string;
  compact?: boolean;
}

export function DrugLikenessPanel({ smiles, compact = false }: DrugLikenessPanelProps) {
  const result = useMemo(() => {
    if (!smiles) return null;
    return calculateDrugLikeness(smiles);
  }, [smiles]);

  if (!result) return null;

  const { lipinski } = result;
  const scoreLabel = getDrugLikenessLabel(result.drugLikenessScore);

  if (compact) {
    return (
      <div className="drug-likeness-compact">
        <div className="drug-likeness-score-badge" style={{ color: scoreLabel.color }}>
          <span className="score-value">{(result.drugLikenessScore * 100).toFixed(0)}</span>
          <span className="score-label">DLS</span>
        </div>
        <div className={`lipinski-badge ${lipinski.passes ? 'pass' : 'fail'}`}>
          Ro5: {lipinski.violations}
        </div>
      </div>
    );
  }

  return (
    <div className="drug-likeness-panel">
      <div className="drug-likeness-header">
        <h4>Drug-Likeness Analysis</h4>
        <div
          className="drug-likeness-score"
          style={{ backgroundColor: scoreLabel.color }}
        >
          {scoreLabel.label}
        </div>
      </div>

      {/* Overall Score */}
      <div className="drug-likeness-overview">
        <div className="overview-score">
          <span className="overview-score-value" style={{ color: scoreLabel.color }}>
            {(result.drugLikenessScore * 100).toFixed(0)}%
          </span>
          <span className="overview-score-label">Drug-Likeness Score</span>
        </div>
        <div className="overview-lipinski">
          <span className={`lipinski-status ${lipinski.passes ? 'pass' : 'fail'}`}>
            {lipinski.passes ? 'Lipinski PASS' : 'Lipinski FAIL'}
          </span>
          <span className="lipinski-violations">
            {lipinski.violations} violation{lipinski.violations !== 1 ? 's' : ''}
          </span>
        </div>
      </div>

      {/* Lipinski Properties */}
      <div className="lipinski-properties">
        <div className="lipinski-property">
          <span className="property-label">MW</span>
          <span className={`property-value ${lipinski.details.mwPass ? 'pass' : 'fail'}`}>
            {lipinski.molecularWeight.toFixed(1)}
          </span>
          <span className="property-limit">≤500</span>
        </div>
        <div className="lipinski-property">
          <span className="property-label">HBD</span>
          <span className={`property-value ${lipinski.details.hbdPass ? 'pass' : 'fail'}`}>
            {lipinski.hBondDonors}
          </span>
          <span className="property-limit">≤5</span>
        </div>
        <div className="lipinski-property">
          <span className="property-label">HBA</span>
          <span className={`property-value ${lipinski.details.hbaPass ? 'pass' : 'fail'}`}>
            {lipinski.hBondAcceptors}
          </span>
          <span className="property-limit">≤10</span>
        </div>
        <div className="lipinski-property">
          <span className="property-label">LogP</span>
          <span className={`property-value ${lipinski.details.logPPass ? 'pass' : 'fail'}`}>
            {lipinski.logP.toFixed(2)}
          </span>
          <span className="property-limit">≤5</span>
        </div>
      </div>

      {/* Additional Properties */}
      <div className="additional-properties">
        <div className="add-property">
          <span className="add-property-label">TPSA</span>
          <span className="add-property-value">{result.properties.tpsa.toFixed(1)} Å²</span>
        </div>
        <div className="add-property">
          <span className="add-property-label">Rot. Bonds</span>
          <span className="add-property-value">{lipinski.rotatableBonds}</span>
        </div>
        <div className="add-property">
          <span className="add-property-label">Rings</span>
          <span className="add-property-value">{result.properties.numRings}</span>
        </div>
        <div className="add-property">
          <span className="add-property-label">Heavy Atoms</span>
          <span className="add-property-value">{result.properties.numHeavyAtoms}</span>
        </div>
      </div>

      {/* Structural Alerts */}
      {result.alerts.length > 0 && (
        <div className="structural-alerts">
          <span className="alerts-label">Structural Alerts:</span>
          <div className="alerts-list">
            {result.alerts.map((alert, i) => (
              <span key={i} className="alert-badge">{alert}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// Compact badge for displaying in molecule cards
interface DrugLikenessBadgeProps {
  smiles: string;
}

export function DrugLikenessBadge({ smiles }: DrugLikenessBadgeProps) {
  const result = useMemo(() => {
    if (!smiles) return null;
    try {
      return calculateDrugLikeness(smiles);
    } catch {
      return null;
    }
  }, [smiles]);

  if (!result) return null;

  const { lipinski } = result;
  const scoreLabel = getDrugLikenessLabel(result.drugLikenessScore);

  return (
    <div className="drug-likeness-badge-row">
      <span
        className="dls-badge"
        style={{ backgroundColor: scoreLabel.color }}
        title={`Drug-Likeness Score: ${(result.drugLikenessScore * 100).toFixed(0)}%`}
      >
        DLS: {(result.drugLikenessScore * 100).toFixed(0)}%
      </span>
      <span
        className={`ro5-badge ${lipinski.passes ? 'pass' : 'fail'}`}
        title={`Lipinski's Rule of Five: ${lipinski.violations} violation(s)`}
      >
        Ro5 {lipinski.passes ? 'Pass' : `(${lipinski.violations})`}
      </span>
    </div>
  );
}
