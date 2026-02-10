/**
 * DataPreviewStep Component
 *
 * Third step: Preview and validate the selected dataset.
 * Shows statistics, distribution, and data quality metrics.
 * Adapts display based on modality (molecular vs protein).
 */

import { useMemo } from 'react';
import { useFineTuning } from '../../../contexts/FineTuningContext';

export function DataPreviewStep() {
  const { dataset, goToNextStep, goToPrevStep, modality } = useFineTuning();

  const isProtein = modality === 'protein';

  // Calculate activity/score distribution
  const activityDistribution = useMemo(() => {
    if (!dataset) return null;

    const validActivities = dataset.molecules
      .filter((m) => m.isValid && m.activity > 0)
      .map((m) => isProtein ? m.activity : Math.log10(m.activity));

    if (validActivities.length === 0) return null;

    const min = Math.floor(Math.min(...validActivities) * 10) / 10;
    const max = Math.ceil(Math.max(...validActivities) * 10) / 10;
    const binCount = 20;
    const binWidth = (max - min) / binCount || 0.1;

    const bins = Array(binCount).fill(0);
    for (const val of validActivities) {
      const binIndex = Math.min(Math.floor((val - min) / binWidth), binCount - 1);
      bins[binIndex]++;
    }

    const maxCount = Math.max(...bins);
    return { bins, min, max, binWidth, maxCount };
  }, [dataset, isProtein]);

  // Sample entries for preview
  const sampleEntries = useMemo(() => {
    if (!dataset) return [];
    return dataset.molecules
      .filter((m) => m.isValid)
      .sort((a, b) => a.activity - b.activity)
      .slice(0, 5);
  }, [dataset]);

  // Sequence length stats for protein
  const seqLengthStats = useMemo(() => {
    if (!dataset || !isProtein) return null;
    const lengths = dataset.molecules.filter((m) => m.isValid).map((m) => m.smiles.length);
    if (lengths.length === 0) return null;
    return {
      min: Math.min(...lengths),
      max: Math.max(...lengths),
      avg: Math.round(lengths.reduce((a, b) => a + b, 0) / lengths.length),
    };
  }, [dataset, isProtein]);

  if (!dataset) {
    return (
      <div className="step-content">
        <div className="content-header">
          <h1 className="content-title">No Dataset Selected</h1>
          <p className="content-subtitle">Please go back and select a dataset.</p>
        </div>
        <div className="step-actions">
          <button className="btn btn-ghost" onClick={goToPrevStep}>
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
          <h1 className="content-title">Data Preview</h1>
          <p className="content-subtitle">
            Review your dataset before training. Source: {dataset.source.toUpperCase()}
            {dataset.sourceId && ` (${dataset.sourceId})`}
          </p>
        </div>
      </div>

      {/* Statistics Cards */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-icon">
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
              <circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth="1.5" />
              <path d="M10 6v4l2.5 1.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
          </div>
          <div className="stat-value">{dataset.totalCount.toLocaleString()}</div>
          <div className="stat-label">Total {isProtein ? 'Sequences' : 'Compounds'}</div>
        </div>

        <div className="stat-card success">
          <div className="stat-icon">
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
              <path d="M4 10l4 4 8-8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <div className="stat-value">{dataset.validCount.toLocaleString()}</div>
          <div className="stat-label">Valid {isProtein ? 'Sequences' : 'SMILES'}</div>
        </div>

        {isProtein && seqLengthStats ? (
          <>
            <div className="stat-card">
              <div className="stat-icon">
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                  <path d="M3 17V7l7-5 7 5v10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
              <div className="stat-value">
                {seqLengthStats.min} - {seqLengthStats.max}
              </div>
              <div className="stat-label">Sequence Length Range</div>
            </div>
            <div className="stat-card">
              <div className="stat-icon">
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                  <rect x="3" y="3" width="14" height="14" rx="2" stroke="currentColor" strokeWidth="1.5" />
                  <path d="M7 10h6M10 7v6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
              </div>
              <div className="stat-value">{seqLengthStats.avg}</div>
              <div className="stat-label">Avg Sequence Length</div>
            </div>
          </>
        ) : (
          <>
            <div className="stat-card">
              <div className="stat-icon">
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                  <path d="M3 17V7l7-5 7 5v10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
              <div className="stat-value">
                {dataset.activityRange.min.toFixed(1)} - {dataset.activityRange.max.toFixed(1)}
              </div>
              <div className="stat-label">Activity Range ({dataset.activityUnit})</div>
            </div>
            <div className="stat-card">
              <div className="stat-icon">
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                  <rect x="3" y="3" width="14" height="14" rx="2" stroke="currentColor" strokeWidth="1.5" />
                  <path d="M7 10h6M10 7v6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
              </div>
              <div className="stat-value">{dataset.activityType}</div>
              <div className="stat-label">Activity Type</div>
            </div>
          </>
        )}
      </div>

      {/* Distribution */}
      {activityDistribution && (
        <div className="card">
          <div className="card-header">
            <h3 className="card-title">{isProtein ? 'Score Distribution' : 'Activity Distribution'}</h3>
            <span className="card-badge">{isProtein ? 'score' : `log10(${dataset.activityUnit})`}</span>
          </div>
          <div className="distribution-chart">
            <div className="histogram">
              {activityDistribution.bins.map((count, i) => (
                <div
                  key={i}
                  className="histogram-bar"
                  style={{
                    height: `${(count / activityDistribution.maxCount) * 100}%`,
                  }}
                  title={`${count} ${isProtein ? 'sequences' : 'compounds'}`}
                />
              ))}
            </div>
            <div className="histogram-axis">
              <span>{activityDistribution.min.toFixed(1)}</span>
              <span>{isProtein ? 'Score' : `log10(${dataset.activityUnit})`}</span>
              <span>{activityDistribution.max.toFixed(1)}</span>
            </div>
          </div>
        </div>
      )}

      {/* Data Split */}
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Data Split</h3>
        </div>
        <div className="data-split">
          <div className="data-split-bar">
            <div
              className="data-split-segment train"
              style={{ width: `${(dataset.splits.train / dataset.validCount) * 100}%` }}
            >
              Training
            </div>
            <div
              className="data-split-segment val"
              style={{ width: `${(dataset.splits.validation / dataset.validCount) * 100}%` }}
            >
              Val
            </div>
            <div
              className="data-split-segment test"
              style={{ width: `${(dataset.splits.test / dataset.validCount) * 100}%` }}
            >
              Test
            </div>
          </div>
          <div className="data-split-legend">
            <span className="legend-item train">
              <span className="legend-dot" />
              Training: {dataset.splits.train.toLocaleString()} (80%)
            </span>
            <span className="legend-item val">
              <span className="legend-dot" />
              Validation: {dataset.splits.validation.toLocaleString()} (10%)
            </span>
            <span className="legend-item test">
              <span className="legend-dot" />
              Test: {dataset.splits.test.toLocaleString()} (10%)
            </span>
          </div>
        </div>
      </div>

      {/* Sample Entries */}
      <div className="card">
        <div className="card-header">
          <h3 className="card-title">Sample {isProtein ? 'Sequences' : 'Compounds'} (Top 5)</h3>
        </div>
        <div className="sample-table">
          <div className="sample-table-header">
            <span className="sample-col smiles">{isProtein ? 'Sequence' : 'SMILES'}</span>
            <span className="sample-col activity">{isProtein ? 'Label / Score' : `Activity (${dataset.activityUnit})`}</span>
            <span className="sample-col status">Status</span>
          </div>
          {sampleEntries.map((mol, i) => (
            <div key={i} className="sample-table-row">
              <span className="sample-col smiles">
                <code>
                  {mol.smiles.length > 50 ? `${mol.smiles.slice(0, 50)}...` : mol.smiles}
                </code>
              </span>
              <span className="sample-col activity">{mol.activity.toFixed(2)}</span>
              <span className="sample-col status">
                {mol.isValid ? (
                  <span className="status-badge valid">Valid</span>
                ) : (
                  <span className="status-badge invalid">Invalid</span>
                )}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Warnings */}
      {dataset.invalidCount > 0 && (
        <div className="alert alert-warning">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path
              d="M8 5v3M8 11h.01M14 8A6 6 0 112 8a6 6 0 0112 0z"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
            />
          </svg>
          <span>
            {dataset.invalidCount} {isProtein ? 'sequence' : 'compound'}{dataset.invalidCount > 1 ? 's' : ''} will be excluded
            due to invalid {isProtein ? 'sequences' : 'SMILES'}
          </span>
        </div>
      )}

      {/* Actions */}
      <div className="step-actions">
        <button className="btn btn-ghost" onClick={goToPrevStep}>
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M12.5 15l-5-5 5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Back
        </button>
        <button className="btn btn-primary btn-lg" onClick={goToNextStep}>
          Continue to Configuration
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M7.5 15l5-5-5-5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>
    </div>
  );
}
